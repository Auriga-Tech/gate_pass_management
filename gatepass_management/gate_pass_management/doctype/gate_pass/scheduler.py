"""Daily maintenance.

Two jobs. Overdue detection is the only genuinely time-driven state transition
in the app: a returnable pass becomes overdue because a date passed, not because
anyone did anything.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, today

from gatepass_management.gate_pass_management.doctype.gate_pass.gate_pass import derive_status
from gatepass_management.gate_pass_management.doctype.gate_pass_event_log.api import log_event
from gatepass_management.utils import guards
from gatepass_management.utils.logger import get_logger


def flag_overdue_returns():
	if not guards.is_enabled():
		return

	settings = guards.get_settings()
	if not settings.enable_returnable:
		return

	overdue = frappe.get_all(
		"Gate Pass",
		filters={
			"docstatus": 1,
			"is_returnable": 1,
			"direction": "Out",
			"expected_return_date": ["<", today()],
			"return_status": ["in", ["Pending", "Partially Returned", "Not Applicable"]],
		},
		fields=["name", "party", "expected_return_date", "total_qty", "returned_qty"],
	)

	for gp in overdue:
		frappe.db.set_value("Gate Pass", gp.name, "return_status", "Overdue", update_modified=False)
		frappe.db.set_value("Gate Pass", gp.name, "status", "Overdue Return", update_modified=False)
		log_event(
			gate_pass=gp.name,
			event="Return Recorded",
			message=_("Marked overdue: expected back on {0}, {1} of {2} returned.").format(
				frappe.format_value(gp.expected_return_date, {"fieldtype": "Date"}),
				flt(gp.returned_qty), flt(gp.total_qty),
			),
		)

	if overdue and settings.notify_overdue_returns:
		_notify_overdue(settings, overdue)

	if overdue:
		get_logger().info("overdue_returns_flagged", extra={"count": len(overdue)})

	_notify_due_soon(settings)


def _notify_due_soon(settings):
	days = cint(settings.overdue_reminder_days_before)
	if not days or not settings.notify_overdue_returns:
		return

	due = frappe.get_all(
		"Gate Pass",
		filters={
			"docstatus": 1,
			"is_returnable": 1,
			"expected_return_date": add_days(today(), days),
			"return_status": ["in", ["Pending", "Partially Returned"]],
		},
		fields=["name", "party", "expected_return_date"],
	)
	if due:
		_send(settings, _("Returnable material due back in {0} day(s)").format(days), due)


def _notify_overdue(settings, rows):
	_send(settings, _("Returnable material is overdue"), rows)


def _send(settings, subject, rows):
	recipients = _recipients(settings)
	if not recipients:
		return

	body = "<ul>" + "".join(
		f"<li>{frappe.utils.get_link_to_form('Gate Pass', r['name'])} — "
		f"{frappe.utils.escape_html(str(r.get('party') or ''))}, "
		f"{_('due')} {frappe.format_value(r['expected_return_date'], {'fieldtype': 'Date'})}</li>"
		for r in rows
	) + "</ul>"

	try:
		frappe.sendmail(recipients=recipients, subject=subject, message=body)
	except Exception:
		frappe.log_error(
			title="Gate Pass: overdue notification failed", message=frappe.get_traceback()
		)


def _recipients(settings) -> list[str]:
	roles = {r.role for r in settings.get("overdue_escalation_roles") or []}
	roles |= {r.role for r in settings.get("notify_roles") or []}
	if not roles:
		return []
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", list(roles)], "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	return [
		u for u in users
		if frappe.db.get_value("User", u, "enabled") and u not in ("Administrator", "Guest")
	]


def refresh_statuses():
	"""Recompute status for open gate passes.

	Cheap safety net: status is derived on every save and on every target event,
	so this exists only to catch documents whose status drifted because something
	changed outside the app's own write paths.
	"""
	if not guards.is_enabled():
		return

	names = frappe.get_all(
		"Gate Pass",
		filters={"docstatus": 1, "status": ["not in", ["Completed", "Closed", "Cancelled"]]},
		pluck="name",
		limit=2000,
	)
	changed = 0
	for name in names:
		doc = frappe.get_doc("Gate Pass", name)
		fresh = derive_status(doc)
		if fresh != doc.status:
			frappe.db.set_value("Gate Pass", name, "status", fresh, update_modified=False)
			changed += 1

	if changed:
		get_logger().info("statuses_refreshed", extra={"changed": changed, "scanned": len(names)})


def flag_stale_drafts():
	"""Surface drafts nobody has submitted.

	A draft left open is material that physically moved with no record anyone
	downstream can see, so it is worth chasing. Controlled by LIFE-STALE-DRAFT,
	which ships Ignore because how long is too long is entirely site-specific.
	"""
	if not guards.is_enabled():
		return

	from gatepass_management.rules.engine import RuleContext

	probe = frappe.new_doc("Gate Pass")
	ctx = RuleContext(probe)
	if not ctx.is_active("LIFE-STALE-DRAFT"):
		return

	days = cint(ctx.threshold("LIFE-STALE-DRAFT", 3))
	if days <= 0:
		return

	cutoff = add_days(today(), -days)
	stale = frappe.get_all(
		"Gate Pass",
		filters={"docstatus": 0, "modified": ["<", cutoff]},
		fields=["name", "party", "posting_date", "owner"],
	)
	if not stale:
		return

	for gp in stale:
		log_event(
			gate_pass=gp.name,
			event="Rule Warned",
			rule_code="LIFE-STALE-DRAFT",
			message=_("Still a draft {0} days after it was last touched.").format(days),
		)

	settings = guards.get_settings()
	recipients = _recipients(settings)
	if recipients:
		body = "<ul>" + "".join(
			f"<li>{frappe.utils.get_link_to_form('Gate Pass', g['name'])} — "
			f"{frappe.utils.escape_html(str(g.get('party') or ''))}</li>"
			for g in stale
		) + "</ul>"
		try:
			frappe.sendmail(
				recipients=recipients,
				subject=_("{0} Gate Pass draft(s) left unsubmitted").format(len(stale)),
				message=body,
			)
		except Exception:
			frappe.log_error(
				title="Gate Pass: stale draft notification failed", message=frappe.get_traceback()
			)

	get_logger().info("stale_drafts_flagged", extra={"count": len(stale), "days": days})
