"""Scheduled cleanup of old audit events."""

import frappe
from frappe.utils import add_days, cint, today

from gate_pass_management.utils.logger import get_logger


def purge_expired():
	"""Delete events past the configured retention period.

	Default is 0 — keep forever. A customer who sets a retention period is making
	a deliberate decision about their own audit trail, so the deletion is
	performed directly rather than going through the on_trash guard.
	"""
	days = cint(frappe.db.get_single_value("Gate Pass Settings", "event_log_retention_days"))
	if days <= 0:
		return

	cutoff = add_days(today(), -days)
	count = frappe.db.count("Gate Pass Event Log", {"event_datetime": ["<", cutoff]})
	if not count:
		return

	frappe.db.delete("Gate Pass Event Log", {"event_datetime": ["<", cutoff]})
	get_logger().info(
		"event_log_purged", extra={"deleted": count, "cutoff": cutoff, "retention_days": days}
	)
