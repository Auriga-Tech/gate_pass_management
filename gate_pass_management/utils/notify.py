"""Notifications.

Gate Pass Settings shipped `notify_on_submit`, `notify_on_block`, `notify_roles`,
`email_template` and `enable_whatsapp`, and nothing read any of them — only the
overdue-return mail in the scheduler ever sent anything. This is the rest.

Sending must never break the thing it is reporting on. A gate pass that was
submitted correctly is still submitted even if the mail server is down, so every
failure here is logged and swallowed. That is the one place in this app where
swallowing is right, and it is deliberate.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import cint, get_link_to_form, get_url_to_form

from gate_pass_management.utils import guards
from gate_pass_management.utils.logger import get_logger


def on_gate_pass_submit(doc):
	settings = guards.get_settings()
	if not cint(settings.notify_on_submit):
		return

	_send(
		settings,
		subject=_("Gate Pass {0} submitted — {1}").format(doc.name, doc.direction),
		intro=_("{0} submitted a {1} gate pass.").format(
			frappe.utils.get_fullname(doc.owner), doc.direction.lower()
		),
		doc=doc,
	)


def on_rule_blocked(doc, violations):
	"""A gate pass someone could not submit.

	Worth telling a supervisor about: a blocked pass means a vehicle is waiting
	and whoever can resolve it may not be the person looking at the screen.
	"""
	settings = guards.get_settings()
	if not cint(settings.notify_on_block) or not violations:
		return

	items = "".join(f"<li>{frappe.utils.escape_html(v.message)}</li>" for v in violations)
	_send(
		settings,
		subject=_("Gate Pass {0} is blocked").format(doc.get("name") or _("(unsaved)")),
		intro=_("{0} could not submit this gate pass:").format(
			frappe.utils.get_fullname(frappe.session.user)
		)
		+ f"<ul>{items}</ul>",
		doc=doc,
	)


def _send(settings, subject: str, intro: str, doc):
	recipients = _recipients(settings)
	if not recipients:
		return

	try:
		if settings.email_template:
			# Frappe's own Email Template rendering, not ours: the template is a stored
			# record that its editors are trusted with, and Frappe renders it in its
			# sandbox. The document's fields are available directly ({{ party }}) and as
			# `doc` ({{ doc.party }}), alongside the `intro` sentence.
			fields = doc.as_dict() if hasattr(doc, "as_dict") else dict(doc)
			formatted = frappe.get_doc("Email Template", settings.email_template).get_formatted_email(
				{**fields, "doc": fields, "intro": intro}
			)
			rendered = formatted["message"]
			subject = formatted["subject"] or subject
		else:
			rendered = _default_body(intro, doc)

		frappe.sendmail(recipients=recipients, subject=subject, message=rendered)
		_whatsapp(settings, recipients, subject, doc)
	except Exception as exc:
		# Never let a notification failure undo the operation it describes.
		get_logger().warning(
			"notification_failed",
			extra={"gate_pass": doc.get("name"), "subject": subject, "error": str(exc)},
		)
		frappe.log_error(
			title="Gate Pass: notification failed",
			message=frappe.get_traceback(),
			reference_doctype="Gate Pass",
			reference_name=doc.get("name"),
		)


def _default_body(intro: str, doc) -> str:
	rows = [
		(_("Direction"), doc.get("direction")),
		(_("Party"), doc.get("party_name") or doc.get("party")),
		(_("Vehicle"), doc.get("vehicle_number")),
		(_("Source"), doc.get("source_document")),
		(_("Total Qty"), doc.get("total_qty")),
	]
	body = "".join(
		f"<tr><td style='padding:2px 12px 2px 0'><b>{label}</b></td>"
		f"<td>{frappe.utils.escape_html(str(value))}</td></tr>"
		for label, value in rows
		if value not in (None, "")
	)
	link = (
		f"<p><a href='{get_url_to_form('Gate Pass', doc.name)}'>{doc.name}</a></p>"
		if doc.get("name")
		else ""
	)
	return f"<p>{intro}</p><table>{body}</table>{link}"


def _whatsapp(settings, recipients: list[str], subject: str, doc):
	"""Only when the frappe_whatsapp app is actually installed.

	The switch is offered unconditionally in Settings, so it has to degrade
	quietly rather than raise on a site that does not have the app.
	"""
	if not cint(settings.enable_whatsapp):
		return
	if "frappe_whatsapp" not in frappe.get_installed_apps():
		return

	for user in recipients:
		number = frappe.db.get_value("User", user, "mobile_no")
		if not number:
			continue
		try:
			frappe.get_doc(
				{
					"doctype": "WhatsApp Message",
					"to": number,
					"message": f"{subject}\n{get_url_to_form('Gate Pass', doc.name)}",
					"reference_doctype": "Gate Pass",
					"reference_name": doc.get("name"),
				}
			).insert(ignore_permissions=True)
		except Exception as exc:
			get_logger().warning(
				"whatsapp_failed", extra={"user": user, "error": str(exc)}
			)


def _recipients(settings) -> list[str]:
	roles = {r.role for r in settings.get("notify_roles") or [] if r.role}
	if not roles:
		return []
	users = frappe.get_all(
		"Has Role",
		filters={"role": ["in", list(roles)], "parenttype": "User"},
		pluck="parent",
		distinct=True,
	)
	return [
		u
		for u in users
		if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")
	]
