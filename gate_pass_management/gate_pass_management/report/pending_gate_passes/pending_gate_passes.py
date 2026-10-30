"""Pending Gate Passes — the store manager's morning worklist.

Material physically arrived, a gate pass records it, and no receipt exists yet.
That gap is the whole reason this app exists, so this report is deliberately the
simplest and most prominent one in the module.

Ageing is the payload. Anything past two days means goods are sitting in the
yard while the books say they have not arrived.
"""

import frappe
from frappe import _
from frappe.query_builder import Criterion
from frappe.query_builder.functions import Sum
from frappe.utils import date_diff, flt, today


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Gate Pass"), "fieldname": "name", "fieldtype": "Link",
		 "options": "Gate Pass", "width": 150},
		{"label": _("Age (Days)"), "fieldname": "age_days", "fieldtype": "Int", "width": 100},
		{"label": _("Bucket"), "fieldname": "bucket", "fieldtype": "Data", "width": 90},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Dir"), "fieldname": "direction", "fieldtype": "Data", "width": 55},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link",
		 "options": "party_type", "width": 160},
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data",
		 "width": 90, "hidden": 1},
		{"label": _("Source"), "fieldname": "source_document", "fieldtype": "Dynamic Link",
		 "options": "source_doctype", "width": 150},
		{"label": _("Source Type"), "fieldname": "source_doctype", "fieldtype": "Data",
		 "width": 100, "hidden": 1},
		{"label": _("Flow"), "fieldname": "source_type", "fieldtype": "Link",
		 "options": "Gate Pass Source", "width": 190},
		{"label": _("Vehicle"), "fieldname": "vehicle_number", "fieldtype": "Data", "width": 110},
		{"label": _("Gate Passed"), "fieldname": "total_qty", "fieldtype": "Float", "width": 105},
		{"label": _("Accepted"), "fieldname": "total_accepted_qty", "fieldtype": "Float",
		 "width": 95},
		{"label": _("Processed"), "fieldname": "processed_qty", "fieldtype": "Float", "width": 95},
		{"label": _("Still Pending"), "fieldname": "pending_qty", "fieldtype": "Float",
		 "width": 110},
		{"label": _("% Done"), "fieldname": "per_processed", "fieldtype": "Percent",
		 "width": 85},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 130},
		{"label": _("Location"), "fieldname": "location", "fieldtype": "Link",
		 "options": "Gate Pass Location", "width": 130},
	]


def get_data(filters):
	GP = frappe.qb.DocType("Gate Pass")

	query = (
		frappe.qb.from_(GP)
		.select(
			GP.name, GP.posting_date, GP.direction, GP.party, GP.party_type,
			GP.source_doctype, GP.source_document, GP.source_type, GP.vehicle_number,
			GP.total_qty, GP.total_accepted_qty, GP.processed_qty, GP.per_processed,
			GP.status, GP.location,
		)
		.where(GP.docstatus == 1)
		.where(GP.per_processed < 100)
		.where(GP.source_type.notnull())
		.orderby(GP.posting_date)
	)

	if filters.get("company"):
		query = query.where(GP.company == filters.company)
	if filters.get("location"):
		query = query.where(GP.location == filters.location)
	if filters.get("direction"):
		query = query.where(GP.direction == filters.direction)
	if filters.get("source_type"):
		query = query.where(GP.source_type == filters.source_type)

	rows = query.run(as_dict=True)
	minimum = int(filters.get("min_age") or 0)
	out = []

	for row in rows:
		row.age_days = date_diff(today(), row.posting_date)
		if row.age_days < minimum:
			continue
		row.bucket = _bucket(row.age_days)
		row.pending_qty = flt(row.total_accepted_qty) - flt(row.processed_qty)
		out.append(row)

	# Oldest first: this is a worklist, not a browse.
	out.sort(key=lambda r: -r.age_days)
	return out


def _bucket(days: int) -> str:
	if days <= 1:
		return _("0-1")
	if days <= 3:
		return _("2-3")
	if days <= 7:
		return _("4-7")
	return _("7+")
