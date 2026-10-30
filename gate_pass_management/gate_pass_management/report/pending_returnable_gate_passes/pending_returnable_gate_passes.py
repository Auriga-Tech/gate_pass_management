"""Pending Returnable Gate Passes — what left and has not come back.

Tools, dies, moulds, cylinders, test equipment. The quiet loss that nobody
notices until it is needed and missing.
"""

import frappe
from frappe import _
from frappe.utils import date_diff, flt, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Gate Pass"), "fieldname": "name", "fieldtype": "Link",
		 "options": "Gate Pass", "width": 150},
		{"label": _("Days Overdue"), "fieldname": "days_overdue", "fieldtype": "Int",
		 "width": 115},
		{"label": _("Bucket"), "fieldname": "bucket", "fieldtype": "Data", "width": 100},
		{"label": _("Out On"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Due Back"), "fieldname": "expected_return_date", "fieldtype": "Date",
		 "width": 100},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link",
		 "options": "party_type", "width": 170},
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data",
		 "width": 90, "hidden": 1},
		{"label": _("Purpose"), "fieldname": "purpose", "fieldtype": "Link",
		 "options": "Gate Pass Purpose", "width": 140},
		{"label": _("Sent"), "fieldname": "total_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Back"), "fieldname": "returned_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Still Out"), "fieldname": "outstanding_qty", "fieldtype": "Float",
		 "width": 95},
		{"label": _("Return Status"), "fieldname": "return_status", "fieldtype": "Data",
		 "width": 130},
		{"label": _("Vehicle"), "fieldname": "vehicle_number", "fieldtype": "Data",
		 "width": 110},
		{"label": _("Location"), "fieldname": "location", "fieldtype": "Link",
		 "options": "Gate Pass Location", "width": 130},
		{"label": _("Remarks"), "fieldname": "remarks", "fieldtype": "Data", "width": 220},
	]


def get_data(filters):
	GP = frappe.qb.DocType("Gate Pass")

	query = (
		frappe.qb.from_(GP)
		.select(
			GP.name, GP.posting_date, GP.expected_return_date, GP.party, GP.party_type,
			GP.purpose, GP.total_qty, GP.returned_qty, GP.return_status,
			GP.vehicle_number, GP.location, GP.remarks,
		)
		.where(GP.docstatus == 1)
		.where(GP.is_returnable == 1)
		.where(GP.return_status.notin(["Returned", "Not Applicable"]))
		.orderby(GP.expected_return_date)
	)

	for field, value in (
		("company", filters.get("company")),
		("location", filters.get("location")),
		("party_type", filters.get("party_type")),
		("party", filters.get("party")),
	):
		if value:
			query = query.where(GP[field] == value)

	rows = query.run(as_dict=True)
	out = []

	for row in rows:
		row.outstanding_qty = flt(row.total_qty) - flt(row.returned_qty)
		row.days_overdue = (
			date_diff(today(), row.expected_return_date) if row.expected_return_date else 0
		)
		row.days_overdue = max(0, row.days_overdue)
		row.bucket = _bucket(row.days_overdue)
		if filters.get("only_overdue") and row.days_overdue <= 0:
			continue
		out.append(row)

	out.sort(key=lambda r: -r.days_overdue)
	return out


def _bucket(days: int) -> str:
	if days <= 0:
		return _("Not Due")
	if days <= 7:
		return _("1-7")
	if days <= 30:
		return _("8-30")
	if days <= 90:
		return _("31-90")
	return _("90+")
