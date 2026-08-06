"""Writing to the audit trail.

The event log is insert-only. No role, including System Manager, has write or
delete permission on it — an audit trail that can be edited is not an audit
trail, and the whole reason this DocType exists is that the implementations this
app replaces allowed a manager to silently rewrite the entry and exit timestamps
of a submitted gate pass with no record of who did it or what the values were.

`log_event` never raises. Losing an audit row is bad; failing the operation the
user was performing because the audit row could not be written is worse, and
would make the logging itself a source of outages. Failures go to the Error Log.
"""

from __future__ import annotations

import json

import frappe
from frappe.utils import now_datetime


def log_event(
	gate_pass: str,
	event: str,
	*,
	message: str = "",
	reason: str = "",
	reference_doctype: str | None = None,
	reference_name: str | None = None,
	field_changed: str | None = None,
	old_value=None,
	new_value=None,
	qty_delta: float | None = None,
	rule_code: str | None = None,
	trace_id: str | None = None,
	error_log: str | None = None,
	values: dict | None = None,
) -> str | None:
	if not gate_pass:
		return None

	try:
		doc = frappe.get_doc(
			{
				"doctype": "Gate Pass Event Log",
				"gate_pass": gate_pass,
				"event": event,
				"event_datetime": now_datetime(),
				"user": frappe.session.user,
				"message": message[:500] if message else "",
				"reason": reason[:500] if reason else "",
				"reference_doctype": reference_doctype,
				"reference_name": reference_name,
				"field_changed": field_changed,
				"old_value": _stringify(old_value),
				"new_value": _stringify(new_value),
				"qty_delta": qty_delta,
				"rule_code": rule_code,
				"trace_id": trace_id,
				"error_log": error_log,
				"values_json": json.dumps(values, default=str) if values else None,
			}
		)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		return doc.name
	except Exception:
		frappe.log_error(
			title="Gate Pass: could not write event log",
			message=frappe.get_traceback(),
			reference_doctype="Gate Pass",
			reference_name=gate_pass,
		)
		return None


def _stringify(value) -> str | None:
	if value is None:
		return None
	if isinstance(value, (dict, list)):
		return json.dumps(value, default=str)[:500]
	return str(value)[:500]


def get_events(gate_pass: str, limit: int = 100) -> list[dict]:
	return frappe.get_all(
		"Gate Pass Event Log",
		filters={"gate_pass": gate_pass},
		fields=[
			"name", "event", "event_datetime", "user", "message", "reason",
			"reference_doctype", "reference_name", "field_changed",
			"old_value", "new_value", "rule_code", "trace_id",
		],
		order_by="event_datetime desc",
		limit=limit,
	)
