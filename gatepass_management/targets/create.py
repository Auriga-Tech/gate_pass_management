"""Creating downstream documents from a gate pass.

Three properties this module guarantees, each of which was violated by the
implementations it replaces:

IDEMPOTENT
    Double-clicking "Create Purchase Receipt" produces one receipt and a clear
    message, not two. Guarded by a lock on the gate pass plus a re-read of
    existing references inside the transaction.

HONEST ABOUT FAILURE
    Batch creation wraps each target in a savepoint. One failure rolls back only
    that target and is REPORTED — the caller gets {"created": [...],
    "failed": [{...}]} and the UI shows both columns. A partial batch is never
    reported as a success.

NEVER BYPASSES VALIDATION
    No `ignore_validate`, no `ignore_mandatory`. If ERPNext refuses to create the
    document, that refusal is the answer and the user sees it. Suppressing those
    flags is how invalid receipts end up in a stock ledger.

The quantity that flows downstream is `accepted_qty`, not `qty`: what the gate
physically took in, not what the paperwork claimed. Damaged quantity maps to the
target's rejected qty where the target supports it.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form, now_datetime

from gatepass_management.gate_pass.doctype.gate_pass_event_log.api import log_event
from gatepass_management.utils.logger import get_logger, log_failure, new_trace_id


@frappe.whitelist()
def create_target(gate_pass: str, target_doctype: str | None = None, raise_on_error: bool = False):
	"""Create the configured target document for a gate pass.

	Returns {"created": [names], "failed": [{"reason", "trace_id"}], "message"}.
	"""
	frappe.has_permission("Gate Pass", "write", gate_pass, throw=True)

	gp = frappe.get_doc("Gate Pass", gate_pass)
	if gp.docstatus != 1:
		frappe.throw(_("Gate Pass must be submitted before a document can be created from it."))

	config = frappe.get_cached_doc("Gate Pass Source", gp.source_type) if gp.source_type else None
	if not config or not config.target_doctype:
		frappe.throw(
			_("No target document is configured for this Gate Pass flow."),
			title=_("Nothing to create"),
		)

	target_doctype = target_doctype or config.target_doctype

	# Serialise concurrent attempts on the same gate pass.
	frappe.db.get_value("Gate Pass", gate_pass, "name", for_update=True)

	existing = _existing_targets(gate_pass, target_doctype)
	remaining = _remaining_by_row(gp, target_doctype)

	if not remaining:
		links = ", ".join(get_link_to_form(target_doctype, n) for n in existing)
		frappe.throw(
			_("Everything on this Gate Pass has already been processed.{0}").format(
				_("<br>Existing documents: {0}").format(links) if links else ""
			),
			title=_("Already processed"),
		)

	created: list[str] = []
	failed: list[dict] = []

	for source_document, rows in _group_by_source(gp, remaining).items():
		savepoint = f"gp_target_{frappe.generate_hash(length=8)}"
		frappe.db.savepoint(savepoint)
		try:
			name = _build_one(gp, config, target_doctype, source_document, rows)
			created.append(name)
		except Exception as exc:
			frappe.db.rollback(save_point=savepoint)
			trace_id = log_failure(
				"target_creation_failed", exc, gate_pass=gate_pass,
				target_doctype=target_doctype, source_document=source_document,
			)
			failed.append(
				{
					"source_document": source_document,
					"reason": str(exc),
					"trace_id": trace_id,
				}
			)
			log_event(
				gate_pass=gate_pass, event="Target Creation Failed",
				message=str(exc)[:500], reference_doctype=target_doctype,
				reference_name=source_document, trace_id=trace_id,
			)
			if raise_on_error:
				# Auto-on-submit: the gate pass has not done its job without its
				# target, so the submit must fail rather than leave a pass that
				# silently produced nothing.
				frappe.throw(
					_("Could not create the {0} for this Gate Pass:<br><br>{1}<br><br>"
					  "Reference: {2}").format(_(target_doctype), str(exc), trace_id),
					title=_("Gate Pass not submitted"),
				)

	_refresh_processed(gp)

	return {
		"created": created,
		"failed": failed,
		"message": _build_message(target_doctype, created, failed),
	}


def _build_one(gp, config, target_doctype, source_document, rows) -> str:
	if config.target_mapper:
		mapper = frappe.get_attr(config.target_mapper)
		target = mapper(gp, source_document, rows)
	else:
		target = _generic_map(gp, config, target_doctype, source_document, rows)

	target.gate_pass = gp.name
	if target.meta.has_field("posting_date") and gp.posting_date:
		target.posting_date = gp.posting_date

	# No ignore_validate, no ignore_mandatory. If ERPNext refuses, the refusal is
	# the answer and it reaches the user verbatim.
	target.insert()

	for row in rows:
		gp.append(
			"references",
			{
				"reference_doctype": target_doctype,
				"reference_name": target.name,
				"reference_row": row.name,
				"qty": flt(row.accepted_qty),
				"link_type": "Target",
				"created_on": now_datetime(),
				"created_by": frappe.session.user,
			},
		)

	gp.flags.ignore_validate_update_after_submit = True
	gp.save(ignore_permissions=True)

	log_event(
		gate_pass=gp.name, event="Target Created",
		reference_doctype=target_doctype, reference_name=target.name,
		qty_delta=sum(flt(r.accepted_qty) for r in rows),
		message=_("Created {0} {1}").format(_(target_doctype), target.name),
	)
	get_logger().info(
		"target_created",
		extra={"gate_pass": gp.name, "target": target.name, "doctype": target_doctype},
	)
	return target.name


def _generic_map(gp, config, target_doctype, source_document, rows):
	"""Map a gate pass onto its target using ERPNext's own mappers where possible.

	Using the stock mapper matters: it brings taxes, currency, terms and company
	defaults that a hand-rolled row copy would silently omit.
	"""
	target = _erpnext_mapper(gp, config, target_doctype, source_document)

	if target is None:
		target = frappe.new_doc(target_doctype)
		target.company = gp.company
		_set_party(target, gp)

	qty_by_source_row = {r.source_row: r for r in rows if r.source_row}

	if target.meta.has_field("items") and qty_by_source_row:
		link_field = _row_link_field(target_doctype)
		keep = []
		for item in target.get("items"):
			source_row = item.get(link_field) if link_field else None
			gp_row = qty_by_source_row.get(source_row)
			if not gp_row:
				continue
			_apply_qty(item, gp_row)
			item.gate_pass_item = gp_row.name
			keep.append(item)
		target.set("items", keep)

	if not target.get("items"):
		frappe.throw(
			_("No rows from {0} could be matched to this Gate Pass. "
			  "Check the Gate Pass Source field mapping.").format(source_document)
		)

	_apply_field_map(gp, config, target)
	return target


def _apply_qty(item, gp_row):
	"""Push the gate's physical count into the target.

	`accepted_qty` — what actually came in — not `qty`, which is what the
	paperwork claimed. Shortage, damage and rejection at the gate together become
	the receipt's Rejected Qty, held in its Rejected Warehouse, so the receipt
	accounts for the whole consignment without a second data-entry step:

	    Accepted Qty  = gate Accepted
	    Rejected Qty  = Shortage + Damaged + Rejected at Gate
	    Received Qty  = Accepted + Rejected Qty   (= the gate Qty)
	"""
	accepted = flt(gp_row.accepted_qty)
	rejected = flt(gp_row.shortage_qty) + flt(gp_row.damaged_qty) + flt(gp_row.rejected_qty)
	item.qty = accepted

	if item.meta.has_field("received_qty"):
		item.received_qty = accepted + rejected
	if item.meta.has_field("rejected_qty"):
		item.rejected_qty = rejected
		if rejected and item.meta.has_field("rejected_warehouse"):
			item.rejected_warehouse = gp_row.rejected_warehouse or frappe.db.get_single_value(
				"Gate Pass Settings", "default_rejected_warehouse"
			)
			if not item.rejected_warehouse:
				frappe.throw(
					_("Row {0} ({1}) has {2} short, damaged or rejected but no Rejected Warehouse. "
					  "Set a Default Rejected Warehouse in Gate Pass Settings, then create the "
					  "receipt again.").format(gp_row.idx, gp_row.item_code, rejected),
					title=_("Rejected Warehouse missing"),
				)
	if item.meta.has_field("amount"):
		item.amount = accepted * flt(item.get("rate"))
	if gp_row.bom and item.meta.has_field("bom"):
		item.bom = gp_row.bom


def _erpnext_mapper(gp, config, target_doctype, source_document):
	"""Delegate to ERPNext's own make_* function when one fits."""
	pairs = {
		("Purchase Order", "Purchase Receipt"):
			"erpnext.buying.doctype.purchase_order.purchase_order.make_purchase_receipt",
		("Subcontracting Order", "Subcontracting Receipt"):
			"erpnext.subcontracting.doctype.subcontracting_order.subcontracting_order."
			"make_subcontracting_receipt",
		("Sales Order", "Delivery Note"):
			"erpnext.selling.doctype.sales_order.sales_order.make_delivery_note",
		("Delivery Note", "Sales Invoice"):
			"erpnext.stock.doctype.delivery_note.delivery_note.make_sales_invoice",
	}
	path = pairs.get((config.source_doctype, target_doctype))
	if not path:
		return None
	try:
		return frappe.get_attr(path)(source_document)
	except ImportError:
		# ERPNext moved the function. Fail loudly with a message an implementer
		# can act on, rather than silently producing an empty document.
		frappe.throw(
			_("This ERPNext version does not expose {0}. Set a custom mapper on the "
			  "Gate Pass Source.").format(path)
		)


def _row_link_field(target_doctype: str) -> str | None:
	return {
		"Purchase Receipt": "purchase_order_item",
		"Subcontracting Receipt": "subcontracting_order_item",
		"Delivery Note": "so_detail",
		"Sales Invoice": "dn_detail",
		"Stock Entry": "ste_detail",
	}.get(target_doctype)


def _set_party(target, gp):
	if not gp.party_type or not gp.party:
		return
	field = frappe.scrub(gp.party_type)
	if target.meta.has_field(field):
		target.set(field, gp.party)


def _apply_field_map(gp, config, target):
	for row in config.get("field_map") or []:
		if row.level != "Header":
			continue
		value = gp.get(row.source_field) or row.default_value
		if value and target.meta.has_field(row.target_field):
			target.set(row.target_field, value)


def _existing_targets(gate_pass: str, target_doctype: str) -> list[str]:
	return frappe.get_all(
		"Gate Pass Reference",
		filters={"parent": gate_pass, "reference_doctype": target_doctype},
		pluck="reference_name",
		distinct=True,
	)


def _remaining_by_row(gp, target_doctype) -> dict[str, float]:
	"""Quantity still to be processed, per gate pass row.

	Counts only references whose target is still alive: a cancelled receipt
	releases its quantity so the gate pass can be processed again.
	"""
	processed: dict[str, float] = {}
	for ref in gp.references:
		if ref.link_type != "Target" or not ref.reference_row:
			continue
		docstatus = frappe.db.get_value(ref.reference_doctype, ref.reference_name, "docstatus")
		if docstatus == 2:
			continue
		processed[ref.reference_row] = processed.get(ref.reference_row, 0) + flt(ref.qty)

	remaining = {}
	for row in gp.items:
		outstanding = flt(row.accepted_qty) - flt(processed.get(row.name, 0))
		if outstanding > 0:
			remaining[row.name] = outstanding
	return remaining


def _group_by_source(gp, remaining: dict[str, float]) -> dict[str, list]:
	grouped: dict[str, list] = {}
	for row in gp.items:
		if row.name not in remaining:
			continue
		grouped.setdefault(row.source_document or gp.source_document, []).append(row)
	return grouped


def _refresh_processed(gp):
	gp.reload()
	total = sum(
		flt(r.qty) for r in gp.references
		if r.link_type == "Target"
		and frappe.db.get_value(r.reference_doctype, r.reference_name, "docstatus") != 2
	)
	from gatepass_management.gate_pass.doctype.gate_pass.gate_pass import (
		compute_per_processed,
		derive_status,
	)

	gp.db_set("processed_qty", total, update_modified=False)
	gp.db_set(
		"per_processed",
		compute_per_processed(total, gp.total_accepted_qty),
		update_modified=False,
	)

	gp.reload()
	gp.db_set("status", derive_status(gp), update_modified=False)


def _build_message(target_doctype, created, failed) -> str:
	parts = []
	if created:
		links = ", ".join(get_link_to_form(target_doctype, n) for n in created)
		parts.append(_("Created: {0}").format(links))
	if failed:
		rows = "".join(
			f"<li>{f['source_document']}: {frappe.utils.escape_html(f['reason'])} "
			f"<span class='text-muted'>({f['trace_id']})</span></li>"
			for f in failed
		)
		parts.append(_("Failed:<ul>{0}</ul>").format(rows))
	return "<br>".join(parts)
