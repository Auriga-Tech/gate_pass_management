"""Compliance Exceptions — dispatches released without a statutory document.

Short report, high stakes. Every row is a decision someone made to let a vehicle
leave without a document the law requires. The point is that it is answerable:
who, when, which gate pass, and what reason they gave.
"""

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("from_date") or not filters.get("to_date"):
		return get_columns(), []
	return get_columns(), get_data(filters)


def get_columns():
	return [
		{"label": _("Gate Pass"), "fieldname": "name", "fieldtype": "Link",
		 "options": "Gate Pass", "width": 150},
		{"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
		{"label": _("Party"), "fieldname": "party", "fieldtype": "Dynamic Link",
		 "options": "party_type", "width": 170},
		{"label": _("Party Type"), "fieldname": "party_type", "fieldtype": "Data",
		 "width": 90, "hidden": 1},
		{"label": _("Source"), "fieldname": "source_document", "fieldtype": "Dynamic Link",
		 "options": "source_doctype", "width": 160},
		{"label": _("Source Type"), "fieldname": "source_doctype", "fieldtype": "Data",
		 "width": 110, "hidden": 1},
		{"label": _("Compliance"), "fieldname": "compliance_status", "fieldtype": "Data",
		 "width": 110},
		{"label": _("Failing Checks"), "fieldname": "failing_checks", "fieldtype": "Data",
		 "width": 220},
		{"label": _("Overridden By"), "fieldname": "compliance_override_by",
		 "fieldtype": "Link", "options": "User", "width": 170},
		{"label": _("Reason Given"), "fieldname": "compliance_override_reason",
		 "fieldtype": "Data", "width": 340},
		{"label": _("Value"), "fieldname": "total_amount", "fieldtype": "Currency",
		 "width": 120},
		{"label": _("Vehicle"), "fieldname": "vehicle_number", "fieldtype": "Data",
		 "width": 110},
	]


def get_data(filters):
	GP = frappe.qb.DocType("Gate Pass")

	query = (
		frappe.qb.from_(GP)
		.select(
			GP.name, GP.posting_date, GP.party, GP.party_type, GP.source_doctype,
			GP.source_document, GP.compliance_status, GP.compliance_override_by,
			GP.compliance_override_reason, GP.total_amount, GP.vehicle_number,
		)
		.where(GP.docstatus == 1)
		.where(GP.posting_date >= filters.from_date)
		.where(GP.posting_date <= filters.to_date)
		.where(
			GP.compliance_override_by.notnull()
			| GP.compliance_status.isin(["Pending", "Failed"])
		)
		.orderby(GP.posting_date, order=frappe.qb.desc)
	)

	if filters.get("company"):
		query = query.where(GP.company == filters.company)
	if filters.get("overridden_by"):
		query = query.where(GP.compliance_override_by == filters.overridden_by)

	rows = query.run(as_dict=True)
	if not rows:
		return []

	failing = _failing_checks([r.name for r in rows])
	for row in rows:
		row.failing_checks = ", ".join(failing.get(row.name, []))
	return rows


def _failing_checks(names: list[str]) -> dict[str, list[str]]:
	checks = frappe.get_all(
		"Gate Pass Compliance Check",
		filters={
			"parent": ["in", names],
			"status": ["in", ["Pending", "Failed", "Provider Unavailable"]],
		},
		fields=["parent", "label", "status"],
	)
	out: dict[str, list[str]] = {}
	for c in checks:
		out.setdefault(c.parent, []).append(f"{c.label} ({c.status})")
	return out
