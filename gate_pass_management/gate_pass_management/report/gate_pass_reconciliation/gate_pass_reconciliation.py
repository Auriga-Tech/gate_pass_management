"""Gate Pass Reconciliation — what was gate passed vs what actually got received.

The report that answers "the gate says 94 arrived, what did the books record?".
Works for every configured flow, not just purchase orders, because it walks the
consumption ledger rather than hard-coding a document pair.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("from_date") or not filters.get("to_date"):
		return get_columns(), []
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Source Type"), "fieldname": "source_doctype", "fieldtype": "Data",
		 "width": 130},
		{"label": _("Source Document"), "fieldname": "source_document",
		 "fieldtype": "Dynamic Link", "options": "source_doctype", "width": 160},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link",
		 "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Gate Pass"), "fieldname": "gate_pass", "fieldtype": "Link",
		 "options": "Gate Pass", "width": 145},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link",
		 "options": "party_type", "width": 150},
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data",
		 "width": 90, "hidden": 1},
		{"label": _("Gate Passed"), "fieldname": "qty", "fieldtype": "Float", "width": 105},
		{"label": _("Accepted"), "fieldname": "accepted_qty", "fieldtype": "Float", "width": 95},
		{"label": _("Short"), "fieldname": "shortage_qty", "fieldtype": "Float", "width": 80},
		{"label": _("Damaged"), "fieldname": "damaged_qty", "fieldtype": "Float", "width": 85},
		{"label": _("Documents"), "fieldname": "target_documents", "fieldtype": "Data",
		 "width": 220},
		{"label": _("Received"), "fieldname": "processed_qty", "fieldtype": "Float",
		 "width": 95},
		{"label": _("Pending"), "fieldname": "pending_qty", "fieldtype": "Float", "width": 95},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM",
		 "width": 70},
	]


def get_data(filters):
	GP = frappe.qb.DocType("Gate Pass")
	GPI = frappe.qb.DocType("Gate Pass Item")

	query = (
		frappe.qb.from_(GPI)
		.inner_join(GP)
		.on(GP.name == GPI.parent)
		.select(
			GPI.name.as_("row_name"), GPI.item_code, GPI.item_name, GPI.qty,
			GPI.accepted_qty, GPI.shortage_qty, GPI.damaged_qty, GPI.uom,
			GPI.source_doctype, GPI.source_document,
			GP.name.as_("gate_pass"), GP.posting_date, GP.party, GP.party_type,
		)
		.where(GP.docstatus == 1)
		.where(GP.posting_date >= filters.from_date)
		.where(GP.posting_date <= filters.to_date)
		.orderby(GPI.source_document)
		.orderby(GPI.item_code)
	)

	for field, value in (
		("company", filters.get("company")),
		("party_type", filters.get("party_type")),
		("party", filters.get("party")),
	):
		if value:
			query = query.where(GP[field] == value)

	if filters.get("source_doctype"):
		query = query.where(GPI.source_doctype == filters.source_doctype)
	if filters.get("source_document"):
		query = query.where(GPI.source_document == filters.source_document)

	rows = query.run(as_dict=True)
	if not rows:
		return []

	# One query for every reference, rather than one per row.
	references = _references_by_row([r.row_name for r in rows])

	out = []
	for row in rows:
		refs = references.get(row.row_name, [])
		row.processed_qty = sum(flt(r["qty"]) for r in refs)
		row.pending_qty = flt(row.accepted_qty) - row.processed_qty
		row.target_documents = ", ".join(sorted({r["reference_name"] for r in refs}))
		if filters.get("only_pending") and row.pending_qty <= 0:
			continue
		out.append(row)

	return out


def _references_by_row(row_names: list[str]) -> dict[str, list[dict]]:
	"""Target documents per gate pass row, excluding cancelled ones."""
	if not row_names:
		return {}

	refs = frappe.get_all(
		"Gate Pass Reference",
		filters={"reference_row": ["in", row_names], "link_type": "Target"},
		fields=["reference_row", "reference_doctype", "reference_name", "qty"],
	)

	# A cancelled receipt releases its quantity, so it must not count as received.
	alive: dict[tuple, bool] = {}
	out: dict[str, list[dict]] = {}
	for ref in refs:
		key = (ref.reference_doctype, ref.reference_name)
		if key not in alive:
			alive[key] = (
				frappe.db.get_value(ref.reference_doctype, ref.reference_name, "docstatus") != 2
			)
		if alive[key]:
			out.setdefault(ref.reference_row, []).append(ref)
	return out
