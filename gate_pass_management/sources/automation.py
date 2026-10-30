"""Auto-created draft gate passes.

When a source document configured for it is submitted, a draft gate pass appears
in the gate's worklist already carrying the items — the operator adds vehicle and
driver, confirms what physically arrived, and submits.

This inverts the workflow. Instead of a guard creating a document from scratch
under time pressure with a truck waiting, they complete and confirm one that is
already correct. Lower friction, and materially better data.

Failure here must never block the source document. A stock entry is a real
business transaction; a convenience draft failing to materialise is not a reason
to refuse it. Failures are logged and surfaced as a warning, never raised.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_link_to_form, today

from gate_pass_management import ledger
from gate_pass_management.utils import guards
from gate_pass_management.utils.logger import get_logger, log_failure


def auto_create_draft(doc, method=None):
	"""Create a draft gate pass for a newly submitted source document."""
	if not guards.is_active(doc):
		return
	if not cint(frappe.db.get_single_value("Gate Pass Settings", "enable_auto_draft_creation")):
		return

	for config in _configs_for(doc.doctype):
		if not _condition_met(config, doc):
			continue
		if _already_exists(config, doc):
			continue
		try:
			_create_one(config, doc)
		except Exception as exc:
			trace_id = log_failure(
				"auto_draft_failed", exc,
				source_doctype=doc.doctype, source_document=doc.name,
				source_config=config.name,
			)
			frappe.msgprint(
				_("A draft Gate Pass could not be created automatically for this {0}. "
				  "Create one manually at the gate. Reference: {1}").format(
					_(doc.doctype), trace_id
				),
				indicator="orange",
				alert=True,
			)


def _configs_for(doctype: str):
	names = frappe.get_all(
		"Gate Pass Source",
		filters={"source_doctype": doctype, "enabled": 1, "auto_create_draft": 1},
		pluck="name",
	)
	return [frappe.get_cached_doc("Gate Pass Source", n) for n in names]


def _condition_met(config, doc) -> bool:
	"""Evaluate the flow's optional Python condition against the source document.

	Sandboxed through Frappe's safe_eval — the condition is configuration
	authored by an implementer, not arbitrary input, but it still has no business
	reaching the filesystem or the database directly.
	"""
	expression = (config.auto_create_condition or "").strip()
	if not expression:
		return True
	try:
		return bool(frappe.safe_eval(expression, None, {"doc": doc, "frappe": frappe._dict()}))
	except Exception as exc:
		get_logger().error(
			"auto_draft_condition_failed",
			extra={"source_config": config.name, "expression": expression, "error": str(exc)},
		)
		return False


def _already_exists(config, doc) -> bool:
	return bool(
		frappe.db.exists(
			"Gate Pass",
			{
				"source_type": config.name,
				"source_document": doc.name,
				"docstatus": ["<", 2],
			},
		)
	)


def _create_one(config, doc):
	pending = ledger.pending_qty(doc.doctype, doc.name, config)
	if not pending or not any(v["pending"] > 0 for v in pending.values()):
		return

	gp = frappe.new_doc("Gate Pass")
	gp.company = doc.get("company")
	gp.source_type = config.name
	gp.source_doctype = doc.doctype
	gp.source_document = doc.name
	gp.source_sub_type = config.sub_type
	gp.direction = config.direction
	gp.gate_pass_type = "Material"
	gp.posting_date = today()
	gp.source_document_date = doc.get("posting_date") or doc.get("transaction_date")

	party_type, party = _resolve_party(config, doc)
	gp.party_type = party_type
	gp.party = party

	child_doctype = frappe.get_meta(doc.doctype).get_field(config.child_table).options
	rows = frappe.get_all(
		child_doctype,
		filters={"parent": doc.name, "parenttype": doc.doctype},
		fields=["*"],
		order_by="idx asc",
	)

	for row in rows:
		info = pending.get(row.name)
		if not info or info["pending"] <= 0:
			continue

		item_code = row.get(config.item_field)
		if item_code and frappe.db.get_value("Item", item_code, "exclude_from_gate_pass"):
			continue

		gp.append(
			"items",
			{
				"item_code": item_code,
				"item_name": row.get("item_name"),
				"uom": row.get(config.uom_field) if config.uom_field else None,
				"conversion_factor": row.get("conversion_factor") or 1,
				"source_qty": info["source_qty"],
				"already_passed_qty": info["consumed"],
				"pending_qty": info["pending"],
				"qty": info["pending"],
				"accepted_qty": info["pending"],
				"rate": row.get(config.rate_field) if config.rate_field else None,
				"warehouse": row.get(config.warehouse_field) if config.warehouse_field else None,
				"bom": row.get(config.bom_field) if config.bom_field else None,
				"source_doctype": doc.doctype,
				"source_document": doc.name,
				"source_row": row.name,
			},
		)

	if not gp.items:
		return

	gp.flags.ignore_permissions = True
	gp.insert(ignore_permissions=True)

	_assign_and_notify(config, gp, doc)

	get_logger().info(
		"auto_draft_created",
		extra={"gate_pass": gp.name, "source": doc.name, "source_config": config.name},
	)
	frappe.msgprint(
		_("Draft Gate Pass {0} created for the gate.").format(get_link_to_form("Gate Pass", gp.name)),
		alert=True,
		indicator="green",
	)


def _resolve_party(config, doc) -> tuple[str | None, str | None]:
	if config.party_type == "Company":
		return "Company", doc.get("company")

	if config.party_type == "From Field" and config.party_field:
		field = config.party_field
		if "." in field:
			# One level of indirection, e.g. subcontracting_order.supplier
			link_field, target_field = field.split(".", 1)
			link_value = doc.get(link_field)
			if not link_value:
				return None, None
			link_doctype = frappe.get_meta(doc.doctype).get_field(link_field).options
			value = frappe.db.get_value(link_doctype, link_value, target_field)
			party_type = frappe.get_meta(link_doctype).get_field(target_field).options
			return party_type, value
		return None, doc.get(field)

	return config.party_type, doc.get(config.party_field) if config.party_field else None


def _assign_and_notify(config, gp, source_doc):
	if not config.auto_create_assign_to_role:
		return

	users = frappe.get_all(
		"Has Role",
		filters={"role": config.auto_create_assign_to_role, "parenttype": "User"},
		pluck="parent",
	)
	users = [
		u for u in users
		if frappe.db.get_value("User", u, "enabled") and u not in ("Administrator", "Guest")
	]
	if not users:
		return

	from frappe.desk.form.assign_to import add as assign

	try:
		assign(
			{
				"assign_to": users[:10],
				"doctype": "Gate Pass",
				"name": gp.name,
				"description": _("Complete the gate pass for {0} {1}").format(
					_(source_doc.doctype), source_doc.name
				),
				"notify": cint(
					frappe.db.get_single_value("Gate Pass Settings", "auto_draft_notify")
				),
			}
		)
	except Exception as exc:
		# An assignment failing must not undo a perfectly good draft.
		get_logger().warning(
			"auto_draft_assign_failed", extra={"gate_pass": gp.name, "error": str(exc)}
		)


def expire_unclaimed_drafts():
	"""Cancel auto-created drafts nobody acted on.

	Without this, a site that auto-creates drafts accumulates a growing list of
	stale ones and the worklist stops being trustworthy. Only auto-created
	drafts are touched — a draft someone typed by hand is their work, not ours
	to discard.
	"""
	days = cint(frappe.db.get_single_value("Gate Pass Settings", "auto_draft_expiry_days"))
	if days <= 0:
		return

	cutoff = add_days(today(), -days)
	stale = frappe.get_all(
		"Gate Pass",
		filters={
			"docstatus": 0,
			"creation": ["<", cutoff],
			"source_type": ["is", "set"],
			"owner": "Administrator",
		},
		pluck="name",
	)

	for name in stale:
		try:
			frappe.delete_doc("Gate Pass", name, ignore_permissions=True, delete_permanently=False)
		except Exception as exc:
			get_logger().warning(
				"stale_draft_cleanup_failed", extra={"gate_pass": name, "error": str(exc)}
			)

	if stale:
		get_logger().info("stale_drafts_removed", extra={"count": len(stale), "cutoff": cutoff})
