"""Reverse guards on ERPNext documents.

These are the enforcement half of the app: rules that run on the Purchase
Receipt, Stock Entry, Delivery Note and friends rather than on the gate pass.

Every handler starts with `guards.is_active()`. When the app is disabled or the
document predates the go-live date, they return immediately and ERPNext behaves
exactly as it did before this app was installed.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form

from gate_pass_management.gate_pass_management.doctype.gate_pass_event_log.api import log_event
from gate_pass_management.rules.engine import RuleContext
from gate_pass_management.utils import guards

# Which field on the target's rows points back at the source document row.
ROW_LINK_FIELDS = {
	"Purchase Receipt": ("purchase_order_item",),
	"Subcontracting Receipt": ("subcontracting_order_item",),
	"Delivery Note": ("so_detail", "against_sales_order_item"),
	"Sales Invoice": ("dn_detail", "so_detail"),
	"Stock Entry": ("ste_detail", "sco_rm_detail"),
}


def _config_for(doc):
	"""The Gate Pass Source whose target is this doctype."""
	names = frappe.get_all(
		"Gate Pass Source",
		filters={"target_doctype": doc.doctype, "enabled": 1},
		pluck="name",
		limit=1,
	)
	return frappe.get_cached_doc("Gate Pass Source", names[0]) if names else None


def validate_target(doc, method=None):
	if not guards.is_active(doc):
		return
	if not doc.meta.has_field("gate_pass"):
		return

	config = _config_for(doc)
	if not config:
		return

	party_type, party = _party_of(doc)
	if guards.is_internal_party(party_type, party):
		# Internal transfers between the customer's own entities. The generic
		# replacement for what one prior implementation hard-coded as a
		# company's legal name inside a SQL WHERE clause.
		return

	ctx = RuleContext(doc, config)

	ctx.check(
		"TGT-REQUIRED",
		config.enforce_on_target == "Required" and not doc.get("gate_pass"),
		_("A Gate Pass is required for this {0}.").format(_(doc.doctype)),
		fieldname="gate_pass",
		remediation=_("Create the Gate Pass at the gate first, then pull items from it."),
	)

	ctx.check(
		"TGT-FORBIDDEN",
		config.enforce_on_target == "Forbidden" and bool(doc.get("gate_pass")),
		_("A Gate Pass should not be linked to this {0}.").format(_(doc.doctype)),
		fieldname="gate_pass",
	)

	ctx.check(
		"TGT-BLOCK-NATIVE",
		bool(config.block_native_target_button)
		and doc.is_new()
		and not doc.get("gate_pass"),
		_("{0} may only be created from a Gate Pass.").format(_(doc.doctype)),
		fieldname="gate_pass",
		remediation=_("Use Get Items From → Gate Pass."),
	)

	if doc.get("gate_pass"):
		_check_row_coverage(doc, ctx)

	ctx.raise_if_blocked()


def _check_row_coverage(doc, ctx):
	"""Every target row must be covered by the gate pass.

	Fails CLOSED. Rows carrying no source reference are reported rather than
	skipped — the prior implementations wrote `if row.ref and row.ref not in
	mapped`, which let unreferenced rows through entirely unchecked.
	"""
	covered = set(
		frappe.get_all(
			"Gate Pass Item",
			filters={"parent": doc.gate_pass},
			pluck="source_row",
		)
	)
	covered.discard(None)
	link_fields = ROW_LINK_FIELDS.get(doc.doctype, ())

	uncovered = []
	unreferenced = []

	for row in doc.get("items") or []:
		source_row = next((row.get(f) for f in link_fields if row.get(f)), None)
		if not source_row:
			unreferenced.append(f"{_('Row')} {row.idx}: {row.get('item_code') or ''}")
		elif source_row not in covered:
			uncovered.append(f"{_('Row')} {row.idx}: {row.get('item_code') or ''}")

	ctx.check(
		"TGT-ROW-COVERAGE",
		bool(uncovered),
		_("These rows are not covered by Gate Pass {0}:<br>{1}").format(
			get_link_to_form("Gate Pass", doc.gate_pass), "<br>".join(uncovered)
		),
		fieldname="items",
	)

	ctx.check(
		"TGT-ROW-COVERAGE",
		bool(unreferenced),
		_("These rows carry no reference to a source document, so they cannot be checked "
		  "against Gate Pass {0}:<br>{1}").format(
			get_link_to_form("Gate Pass", doc.gate_pass), "<br>".join(unreferenced)
		),
		fieldname="items",
	)


def before_submit_target(doc, method=None):
	if not guards.is_active(doc) or not doc.meta.has_field("gate_pass"):
		return
	if not doc.get("gate_pass"):
		return

	config = _config_for(doc)
	ctx = RuleContext(doc, config)

	# Serialise concurrent receipts drawing on the same gate pass.
	frappe.db.get_value("Gate Pass", doc.gate_pass, "name", for_update=True)

	_check_row_quantities(doc, ctx)
	_check_total_quantity(doc, ctx)
	ctx.raise_if_blocked()


def _check_row_quantities(doc, ctx):
	"""Per source row, not per document total.

	Checking only the header total permits receiving 100 of item A against a
	50/50 gate pass — the quantities balance while the actual goods do not.
	"""
	gp_rows = {
		r.source_row: r
		for r in frappe.get_all(
			"Gate Pass Item",
			filters={"parent": doc.gate_pass},
			fields=["name", "source_row", "item_code", "accepted_qty"],
		)
		if r.source_row
	}
	if not gp_rows:
		return

	link_fields = ROW_LINK_FIELDS.get(doc.doctype, ())
	tolerance = flt(ctx.threshold("TGT-QTY-ROW", 0))

	already = _already_processed(doc)

	for row in doc.get("items") or []:
		source_row = next((row.get(f) for f in link_fields if row.get(f)), None)
		gp_row = gp_rows.get(source_row)
		if not gp_row:
			continue

		allowed = flt(gp_row.accepted_qty) * (1 + tolerance / 100.0)
		total = flt(already.get(source_row, 0)) + flt(row.qty)

		ctx.check(
			"TGT-QTY-ROW",
			flt(total, 6) > flt(allowed, 6),
			_("Item {0}: total {1} against Gate Pass {2} exceeds the gate-passed qty {3}.").format(
				row.get("item_code"), flt(total, 3),
				get_link_to_form("Gate Pass", doc.gate_pass), flt(gp_row.accepted_qty, 3),
			),
			row_idx=row.idx, fieldname="qty",
		)


def _already_processed(doc) -> dict[str, float]:
	"""Quantity already taken from this gate pass by other submitted targets."""
	link_fields = ROW_LINK_FIELDS.get(doc.doctype, ())
	if not link_fields:
		return {}

	others = frappe.get_all(
		doc.doctype,
		filters={"gate_pass": doc.gate_pass, "docstatus": 1, "name": ["!=", doc.name or ""]},
		pluck="name",
	)
	if not others:
		return {}

	child_doctype = frappe.get_meta(doc.doctype).get_field("items").options
	rows = frappe.get_all(
		child_doctype,
		filters={"parent": ["in", others]},
		fields=["qty", *link_fields],
	)

	totals: dict[str, float] = {}
	for row in rows:
		key = next((row.get(f) for f in link_fields if row.get(f)), None)
		if key:
			totals[key] = totals.get(key, 0) + flt(row.qty)
	return totals


def _check_total_quantity(doc, ctx):
	gp_total = flt(
		frappe.db.get_value("Gate Pass", doc.gate_pass, "total_accepted_qty")
	)
	if not gp_total:
		return

	others = frappe.get_all(
		doc.doctype,
		filters={"gate_pass": doc.gate_pass, "docstatus": 1, "name": ["!=", doc.name or ""]},
		pluck="name",
	)
	already = 0.0
	if others:
		child_doctype = frappe.get_meta(doc.doctype).get_field("items").options
		already = flt(
			frappe.db.get_value(
				child_doctype, {"parent": ["in", others]}, "sum(qty)", as_dict=False
			)
			or 0
		)

	current = sum(flt(r.qty) for r in doc.get("items") or [])
	tolerance = flt(ctx.threshold("TGT-QTY-TOTAL", 0))
	allowed = gp_total * (1 + tolerance / 100.0)

	ctx.check(
		"TGT-QTY-TOTAL",
		flt(already + current, 6) > flt(allowed, 6),
		_("Total qty {0} against Gate Pass {1} exceeds its accepted qty {2}.").format(
			flt(already + current, 3), get_link_to_form("Gate Pass", doc.gate_pass), gp_total
		),
	)


def on_submit_target(doc, method=None):
	if not guards.is_active(doc) or not doc.get("gate_pass"):
		return
	_sync_gate_pass(doc.gate_pass)
	log_event(
		gate_pass=doc.gate_pass, event="Target Created",
		reference_doctype=doc.doctype, reference_name=doc.name,
		message=_("{0} {1} submitted against this Gate Pass.").format(_(doc.doctype), doc.name),
	)


def on_cancel_target(doc, method=None):
	if not doc.meta.has_field("gate_pass") or not doc.get("gate_pass"):
		return
	# Release the quantity so the gate pass can be processed again.
	_remove_references(doc)
	_sync_gate_pass(doc.gate_pass)
	log_event(
		gate_pass=doc.gate_pass, event="Target Cancelled",
		reference_doctype=doc.doctype, reference_name=doc.name,
	)
	_ignore_gate_pass_link(doc)


def on_trash_target(doc, method=None):
	if not doc.meta.has_field("gate_pass") or not doc.get("gate_pass"):
		return
	_remove_references(doc)
	_sync_gate_pass(doc.gate_pass)
	_ignore_gate_pass_link(doc)


def _remove_references(doc):
	rows = frappe.get_all(
		"Gate Pass Reference",
		filters={
			"parent": doc.gate_pass,
			"reference_doctype": doc.doctype,
			"reference_name": doc.name,
		},
		pluck="name",
	)
	for name in rows:
		frappe.db.delete("Gate Pass Reference", name)


def _sync_gate_pass(gate_pass: str):
	from gate_pass_management.gate_pass_management.doctype.gate_pass.gate_pass import (
		compute_per_processed,
		derive_status,
	)

	gp = frappe.get_doc("Gate Pass", gate_pass)
	total = 0.0
	for ref in gp.references:
		if ref.link_type != "Target":
			continue
		if frappe.db.get_value(ref.reference_doctype, ref.reference_name, "docstatus") == 2:
			continue
		total += flt(ref.qty)

	gp.db_set("processed_qty", total, update_modified=False)
	gp.db_set(
		"per_processed",
		compute_per_processed(total, gp.total_accepted_qty),
		update_modified=False,
	)
	gp.reload()
	gp.db_set("status", derive_status(gp), update_modified=False)


def _ignore_gate_pass_link(doc):
	"""Keep Frappe's generic link check quiet so our own messages surface instead.

	ERPNext sets `ignore_linked_doctypes` itself in its own `on_cancel`, as a
	TUPLE of its ledger doctypes — GL Entry, Stock Ledger Entry, Repost Item
	Valuation and friends. Add to whatever is already there rather than testing
	for a list and replacing it: a tuple fails that test, so replacing it threw
	ERPNext's own exclusions away and cancelling a receipt then failed on its own
	ledger entries.
	"""
	ignored = list(getattr(doc, "ignore_linked_doctypes", None) or [])
	if "Gate Pass" not in ignored:
		ignored.append("Gate Pass")
	doc.ignore_linked_doctypes = ignored


def _party_of(doc) -> tuple[str | None, str | None]:
	for party_type, field in (("Supplier", "supplier"), ("Customer", "customer"), (None, "party")):
		if not doc.meta.has_field(field) or not doc.get(field):
			continue
		if party_type:
			return party_type, doc.get(field)
		# A `party` field carries its own type: a Dynamic Link names the field
		# holding it, a plain Link names the doctype outright.
		df = doc.meta.get_field(field)
		if df.fieldtype == "Dynamic Link":
			return doc.get(df.options), doc.get(field)
		if df.fieldtype == "Link":
			return df.options, doc.get(field)
	return None, None
