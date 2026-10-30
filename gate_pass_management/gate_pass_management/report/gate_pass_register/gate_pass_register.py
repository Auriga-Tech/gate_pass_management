"""Gate Pass Register — the statutory register.

One row per item per gate pass: everything that crossed the boundary in a
period. This is what an auditor asks for, and what a plant produces when a
customer or a regulator wants to see movement history.
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
		{"label": _("Gate Pass"), "fieldname": "gate_pass", "fieldtype": "Link",
		 "options": "Gate Pass", "width": 150},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Time"), "fieldname": "posting_time", "fieldtype": "Time", "width": 80},
		{"label": _("Dir"), "fieldname": "direction", "fieldtype": "Data", "width": 55},
		{"label": _("Type"), "fieldname": "gate_pass_type", "fieldtype": "Data", "width": 110},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 120},
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data", "width": 90},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link",
		 "options": "party_type", "width": 150},
		{"label": _("Party Name"), "fieldname": "party_name", "fieldtype": "Data", "width": 170},
		{"label": _("Source"), "fieldname": "source_document", "fieldtype": "Dynamic Link",
		 "options": "source_doctype", "width": 150},
		{"label": _("Source Type"), "fieldname": "source_doctype", "fieldtype": "Data",
		 "width": 110, "hidden": 1},
		{"label": _("Ref / Challan No"), "fieldname": "reference_no", "fieldtype": "Data",
		 "width": 130},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link",
		 "options": "Item", "width": 140},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 90},
		{"label": _("Accepted"), "fieldname": "accepted_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Short"), "fieldname": "shortage_qty", "fieldtype": "Float", "width": 80},
		{"label": _("Damaged"), "fieldname": "damaged_qty", "fieldtype": "Float", "width": 85},
		{"label": _("Rejected"), "fieldname": "rejected_qty", "fieldtype": "Float", "width": 85},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM",
		 "width": 70},
		{"label": _("Vehicle"), "fieldname": "vehicle_number", "fieldtype": "Data", "width": 110},
		{"label": _("Driver"), "fieldname": "driver_name", "fieldtype": "Data", "width": 130},
		{"label": _("Gate"), "fieldname": "gate", "fieldtype": "Link", "options": "Gate",
		 "width": 110},
		{"label": _("Location"), "fieldname": "location", "fieldtype": "Link",
		 "options": "Gate Pass Location", "width": 130},
		{"label": _("Entry"), "fieldname": "entry_datetime", "fieldtype": "Datetime",
		 "width": 150},
		{"label": _("Exit"), "fieldname": "exit_datetime", "fieldtype": "Datetime", "width": 150},
		{"label": _("Officer"), "fieldname": "security_officer_name", "fieldtype": "Data",
		 "width": 140},
		{"label": _("Created By"), "fieldname": "owner", "fieldtype": "Link",
		 "options": "User", "width": 140},
	]


def get_data(filters):
	GP = frappe.qb.DocType("Gate Pass")
	GPI = frappe.qb.DocType("Gate Pass Item")

	query = (
		frappe.qb.from_(GP)
		.left_join(GPI)
		.on(GPI.parent == GP.name)
		.select(
			GP.name.as_("gate_pass"), GP.posting_date, GP.posting_time, GP.direction,
			GP.gate_pass_type, GP.status, GP.party_type, GP.party, GP.party_name,
			GP.source_doctype, GP.source_document, GP.reference_no, GP.vehicle_number,
			GP.driver_name, GP.gate, GP.location, GP.entry_datetime, GP.exit_datetime,
			GP.security_officer_name, GP.owner,
			GPI.item_code, GPI.item_name, GPI.qty, GPI.accepted_qty,
			GPI.shortage_qty, GPI.damaged_qty, GPI.rejected_qty, GPI.uom,
		)
		.where(GP.docstatus == 1)
		.where(GP.posting_date >= filters.from_date)
		.where(GP.posting_date <= filters.to_date)
		.orderby(GP.posting_date)
		.orderby(GP.name)
		.orderby(GPI.idx)
	)

	for field, value in (
		("company", filters.get("company")),
		("location", filters.get("location")),
		("direction", filters.get("direction")),
		("party_type", filters.get("party_type")),
		("party", filters.get("party")),
		("gate", filters.get("gate")),
		("status", filters.get("status")),
		("owner", filters.get("created_by")),
	):
		if value:
			query = query.where(GP[field] == value)

	if filters.get("vehicle_number"):
		query = query.where(GP.vehicle_number.like(f"%{filters.vehicle_number}%"))
	if filters.get("item_code"):
		query = query.where(GPI.item_code == filters.item_code)

	return query.run(as_dict=True)
