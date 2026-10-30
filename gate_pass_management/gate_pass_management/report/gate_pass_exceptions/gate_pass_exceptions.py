"""Gate Pass Exceptions — every rule that fired as a warning.

The most valuable report in the app for anyone improving a process. Advisory
mode records rather than blocks, and this is where those recordings surface:
which rule, how often, by whom, and what reason they gave.

Use it to decide what to tighten. If a rule warns 200 times a month, either the
process is broken or the rule is wrong — and either way you now know.
"""

import json

import frappe
from frappe import _


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.get("from_date") or not filters.get("to_date"):
		return get_columns(), [], None, None
	data = get_data(filters)
	return get_columns(), data, _summary(data), _chart(data)


def get_columns():
	return [
		{"label": _("When"), "fieldname": "event_datetime", "fieldtype": "Datetime",
		 "width": 155},
		{"label": _("Gate Pass"), "fieldname": "gate_pass", "fieldtype": "Link",
		 "options": "Gate Pass", "width": 145},
		{"label": _("Event"), "fieldname": "event", "fieldtype": "Data", "width": 150},
		{"label": _("Rule"), "fieldname": "rule_code", "fieldtype": "Data", "width": 170},
		{"label": _("User"), "fieldname": "user", "fieldtype": "Link", "options": "User",
		 "width": 160},
		{"label": _("What Happened"), "fieldname": "message", "fieldtype": "Data",
		 "width": 400},
		{"label": _("Reason Given"), "fieldname": "reason", "fieldtype": "Data", "width": 280},
		{"label": _("Trace"), "fieldname": "trace_id", "fieldtype": "Data", "width": 110},
	]


def get_data(filters):
	EL = frappe.qb.DocType("Gate Pass Event Log")

	exception_events = [
		"Rule Warned", "Validation Failed", "Compliance Overridden",
		"Timestamp Amended", "Discrepancy Recorded", "Target Creation Failed",
		"Attachment Removed",
	]

	query = (
		frappe.qb.from_(EL)
		.select(
			EL.event_datetime, EL.gate_pass, EL.event, EL.rule_code, EL.user,
			EL.message, EL.reason, EL.trace_id,
		)
		.where(EL.event_datetime >= filters.from_date)
		.where(EL.event_datetime <= f"{filters.to_date} 23:59:59")
		.orderby(EL.event_datetime, order=frappe.qb.desc)
		.limit(5000)
	)

	if filters.get("event"):
		query = query.where(EL.event == filters.event)
	else:
		query = query.where(EL.event.isin(exception_events))

	if filters.get("rule_code"):
		query = query.where(EL.rule_code == filters.rule_code)
	if filters.get("user"):
		query = query.where(EL.user == filters.user)

	return query.run(as_dict=True)


def _summary(data):
	if not data:
		return None
	rules = {r.rule_code for r in data if r.rule_code}
	users = {r.user for r in data if r.user}
	return [
		{"value": len(data), "label": _("Exceptions"), "datatype": "Int"},
		{"value": len(rules), "label": _("Distinct Rules"), "datatype": "Int"},
		{"value": len(users), "label": _("Users Involved"), "datatype": "Int"},
	]


def _chart(data):
	"""Which rules fire most — the shortlist of what to fix or tighten."""
	if not data:
		return None

	counts: dict[str, int] = {}
	for row in data:
		key = row.rule_code or row.event
		counts[key] = counts.get(key, 0) + 1

	top = sorted(counts, key=lambda k: -counts[k])[:10]
	return {
		"data": {
			"labels": top,
			"datasets": [{"name": _("Times Fired"), "values": [counts[k] for k in top]}],
		},
		"type": "bar",
		"colors": ["#f0972a"],
	}
