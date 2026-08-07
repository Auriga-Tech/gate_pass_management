"""Discrepancy Register — shortage, damage and rejection by cause and liability.

This is the report that turns recorded damage into money: a supplier scorecard,
a transporter claim, or evidence in a dispute. Grouping by liable party is what
makes it actionable rather than merely descriptive.
"""

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("from_date") or not filters.get("to_date"):
		return get_columns(), [], None, None
	data = get_data(filters)
	return get_columns(), data, None, get_chart(data)


def get_columns():
	return [
		{"label": _("Gate Pass"), "fieldname": "gate_pass", "fieldtype": "Link",
		 "options": "Gate Pass", "width": 145},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link",
		 "options": "party_type", "width": 160},
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data",
		 "width": 90, "hidden": 1},
		{"label": _("Transporter"), "fieldname": "transporter", "fieldtype": "Link",
		 "options": "Supplier", "width": 150},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link",
		 "options": "Item", "width": 150},
		{"label": _("Reason"), "fieldname": "discrepancy_reason", "fieldtype": "Link",
		 "options": "Gate Pass Discrepancy Reason", "width": 170},
		{"label": _("Category"), "fieldname": "category", "fieldtype": "Data", "width": 110},
		{"label": _("Liable"), "fieldname": "liable_party", "fieldtype": "Data", "width": 110},
		{"label": _("Gate Passed"), "fieldname": "qty", "fieldtype": "Float", "width": 105},
		{"label": _("Short"), "fieldname": "shortage_qty", "fieldtype": "Float", "width": 85},
		{"label": _("Damaged"), "fieldname": "damaged_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Rejected"), "fieldname": "rejected_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Total Affected"), "fieldname": "affected_qty", "fieldtype": "Float",
		 "width": 115},
		{"label": _("% of Line"), "fieldname": "affected_pct", "fieldtype": "Percent",
		 "width": 95},
		{"label": _("Value"), "fieldname": "affected_value", "fieldtype": "Currency",
		 "width": 110},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM",
		 "width": 70},
		{"label": _("Vehicle"), "fieldname": "vehicle_number", "fieldtype": "Data",
		 "width": 110},
		{"label": _("Notes"), "fieldname": "discrepancy_notes", "fieldtype": "Data",
		 "width": 240},
	]


def get_data(filters):
	GP = frappe.qb.DocType("Gate Pass")
	GPI = frappe.qb.DocType("Gate Pass Item")
	R = frappe.qb.DocType("Gate Pass Discrepancy Reason")

	query = (
		frappe.qb.from_(GPI)
		.inner_join(GP)
		.on(GP.name == GPI.parent)
		.left_join(R)
		.on(R.name == GPI.discrepancy_reason)
		.select(
			GP.name.as_("gate_pass"), GP.posting_date, GP.party, GP.party_type,
			GP.transporter, GP.vehicle_number, GP.discrepancy_notes,
			GPI.item_code, GPI.qty, GPI.rate, GPI.uom,
			GPI.shortage_qty, GPI.damaged_qty, GPI.rejected_qty, GPI.discrepancy_reason,
			R.category, R.liable_party,
		)
		.where(GP.docstatus == 1)
		.where(GP.posting_date >= filters.from_date)
		.where(GP.posting_date <= filters.to_date)
		.where(
			(GPI.shortage_qty > 0) | (GPI.damaged_qty > 0) | (GPI.rejected_qty > 0)
		)
		.orderby(GP.posting_date, order=frappe.qb.desc)
	)

	for field, value in (
		("company", filters.get("company")),
		("location", filters.get("location")),
		("party_type", filters.get("party_type")),
		("party", filters.get("party")),
		("transporter", filters.get("transporter")),
	):
		if value:
			query = query.where(GP[field] == value)

	if filters.get("discrepancy_reason"):
		query = query.where(GPI.discrepancy_reason == filters.discrepancy_reason)
	if filters.get("item_code"):
		query = query.where(GPI.item_code == filters.item_code)
	if filters.get("category"):
		query = query.where(R.category == filters.category)
	if filters.get("liable_party"):
		query = query.where(R.liable_party == filters.liable_party)

	rows = query.run(as_dict=True)

	for row in rows:
		row.affected_qty = flt(row.shortage_qty) + flt(row.damaged_qty) + flt(row.rejected_qty)
		row.affected_pct = (row.affected_qty / flt(row.qty) * 100) if flt(row.qty) else 0
		row.affected_value = row.affected_qty * flt(row.rate)

	return rows


def get_chart(data):
	"""Affected quantity by liable party — who is actually costing you."""
	if not data:
		return None

	totals: dict[str, float] = {}
	for row in data:
		key = row.get("liable_party") or _("Unknown")
		totals[key] = totals.get(key, 0) + flt(row.get("affected_qty"))

	labels = sorted(totals, key=lambda k: -totals[k])
	return {
		"data": {
			"labels": labels,
			"datasets": [{"name": _("Affected Qty"), "values": [totals[k] for k in labels]}],
		},
		"type": "bar",
		"colors": ["#e24c4c"],
	}
