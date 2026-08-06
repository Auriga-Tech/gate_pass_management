"""Attachment immutability on submitted gate passes.

Making an Attach field read-only does not stop removal: the file is a separate
File document whose deletion is governed by File permissions, not by the parent
field's state. So the guard lives on File.on_trash.

Unlike the implementation this replaces, which threw for every deletion with no
override at all, this is role-gated. Attachments do get scanned upside-down and
uploaded to the wrong row; forcing a cancel-and-amend for that is worse than
allowing a recorded correction. Every removal writes an event.
"""

from __future__ import annotations

import frappe
from frappe import _

from gatepass_management.gate_pass.doctype.gate_pass_event_log.api import log_event
from gatepass_management.utils import guards


def prevent_delete_on_submit(doc, method=None):
	if doc.attached_to_doctype != "Gate Pass" or not doc.attached_to_name:
		return
	if not guards.is_enabled():
		return

	settings = guards.get_settings()
	if not settings.lock_attachments_on_submit:
		return

	docstatus = frappe.db.get_value("Gate Pass", doc.attached_to_name, "docstatus")
	if docstatus != 1:
		return

	allowed = {r.role for r in settings.get("attachment_unlock_roles") or []}
	if allowed & set(frappe.get_roles()):
		log_event(
			gate_pass=doc.attached_to_name,
			event="Attachment Removed",
			message=_("Removed {0} from a submitted Gate Pass.").format(doc.file_name),
			field_changed="attachment",
			old_value=doc.file_url,
		)
		return

	frappe.throw(
		_("Attachments on a submitted Gate Pass cannot be removed. "
		  "Ask a Gate Pass Manager, or cancel the Gate Pass first."),
		title=_("Attachment is locked"),
	)
