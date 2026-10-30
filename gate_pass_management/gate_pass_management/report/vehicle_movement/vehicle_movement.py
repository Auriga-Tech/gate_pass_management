"""Vehicle Movement — dwell time at the gate.

Turnaround is the operational metric a gate actually controls. Long dwell means
vehicles queuing, demurrage, and unhappy transporters.
"""

import frappe
from frappe import _
from frappe.utils import flt, get_datetime, time_diff_in_hours


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("from_date") or not filters.get("to_date"):
		return get_columns(filters), []
	data = get_data(filters)
	if filters.get("group_by_vehicle"):
		data = summarise(data)
	return get_columns(filters), data


def get_columns(filters):
	if filters.get("group_by_vehicle"):
		return [
			{"label": _("Vehicle"), "fieldname": "vehicle_number", "fieldtype": "Data",
			 "width": 140},
			{"label": _("Transporter"), "fieldname": "transporter", "fieldtype": "Link",
			 "options": "Supplier", "width": 170},
			{"label": _("Trips"), "fieldname": "trips", "fieldtype": "Int", "width": 80},
			{"label": _("In"), "fieldname": "inward", "fieldtype": "Int", "width": 70},
			{"label": _("Out"), "fieldname": "outward", "fieldtype": "Int", "width": 70},
			{"label": _("Total Qty"), "fieldname": "total_qty", "fieldtype": "Float",
			 "width": 110},
			{"label": _("Avg Dwell (Hrs)"), "fieldname": "avg_dwell", "fieldtype": "Float",
			 "width": 130, "precision": 2},
			{"label": _("Max Dwell (Hrs)"), "fieldname": "max_dwell", "fieldtype": "Float",
			 "width": 130, "precision": 2},
		]

	return [
		{"label": _("Gate Pass"), "fieldname": "name", "fieldtype": "Link",
		 "options": "Gate Pass", "width": 150},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Dir"), "fieldname": "direction", "fieldtype": "Data", "width": 55},
		{"label": _("Vehicle"), "fieldname": "vehicle_number", "fieldtype": "Data",
		 "width": 130},
		{"label": _("Type"), "fieldname": "vehicle_type", "fieldtype": "Data", "width": 100},
		{"label": _("Transporter"), "fieldname": "transporter", "fieldtype": "Link",
		 "options": "Supplier", "width": 160},
		{"label": _("Driver"), "fieldname": "driver_name", "fieldtype": "Data", "width": 140},
		{"label": _("Entry"), "fieldname": "entry_datetime", "fieldtype": "Datetime",
		 "width": 155},
		{"label": _("Exit"), "fieldname": "exit_datetime", "fieldtype": "Datetime",
		 "width": 155},
		{"label": _("Dwell (Hrs)"), "fieldname": "dwell_hours", "fieldtype": "Float",
		 "width": 110, "precision": 2},
		{"label": _("Qty"), "fieldname": "total_qty", "fieldtype": "Float", "width": 90},
		{"label": _("Gate"), "fieldname": "gate", "fieldtype": "Link", "options": "Gate",
		 "width": 110},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link",
		 "options": "party_type", "width": 150},
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data",
		 "width": 90, "hidden": 1},
	]


def get_data(filters):
	GP = frappe.qb.DocType("Gate Pass")

	query = (
		frappe.qb.from_(GP)
		.select(
			GP.name, GP.posting_date, GP.direction, GP.vehicle_number, GP.vehicle_type,
			GP.transporter, GP.driver_name, GP.entry_datetime, GP.exit_datetime,
			GP.total_qty, GP.gate, GP.party, GP.party_type,
		)
		.where(GP.docstatus == 1)
		.where(GP.posting_date >= filters.from_date)
		.where(GP.posting_date <= filters.to_date)
		.where(GP.vehicle_number.notnull())
		.where(GP.vehicle_number != "")
		.orderby(GP.posting_date, order=frappe.qb.desc)
	)

	for field, value in (
		("company", filters.get("company")),
		("location", filters.get("location")),
		("transporter", filters.get("transporter")),
	):
		if value:
			query = query.where(GP[field] == value)

	if filters.get("vehicle_number"):
		query = query.where(GP.vehicle_number.like(f"%{filters.vehicle_number}%"))

	rows = query.run(as_dict=True)
	for row in rows:
		row.dwell_hours = _dwell(row.entry_datetime, row.exit_datetime)
	return rows


def _dwell(entry, exit_):
	"""Hours between entry and exit, when both are known."""
	if not entry or not exit_:
		return 0
	hours = time_diff_in_hours(exit_, entry)
	# A negative dwell means the stamps were amended inconsistently; report zero
	# rather than a nonsense figure that would skew every average.
	return max(0, flt(hours, 2))


def summarise(rows):
	grouped: dict[str, dict] = {}
	for row in rows:
		key = row.vehicle_number
		g = grouped.setdefault(key, {
			"vehicle_number": key, "transporter": row.transporter, "trips": 0,
			"inward": 0, "outward": 0, "total_qty": 0.0,
			"_dwells": [], "avg_dwell": 0.0, "max_dwell": 0.0,
		})
		g["trips"] += 1
		g["inward" if row.direction == "In" else "outward"] += 1
		g["total_qty"] += flt(row.total_qty)
		if row.dwell_hours:
			g["_dwells"].append(row.dwell_hours)

	out = []
	for g in grouped.values():
		dwells = g.pop("_dwells")
		if dwells:
			g["avg_dwell"] = flt(sum(dwells) / len(dwells), 2)
			g["max_dwell"] = max(dwells)
		out.append(g)

	out.sort(key=lambda r: -r["trips"])
	return out
