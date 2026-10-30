"""Cascade cancellation.

Only used when the customer explicitly chooses "Cascade Cancel Targets" in
Settings. It is not the default: cascading silently reverses stock ledger
entries, which is a dangerous thing to do without the user seeing the list first.

Re-entrancy is guarded by an explicit context manager rather than a global
`frappe.flags` value or a string match on `frappe.form_dict["cmd"]`. Both of
those were used by the implementations this app replaces; both break in
background jobs, API calls and tests, where form_dict is empty and flags leak
between jobs sharing a worker process.
"""

from __future__ import annotations

import contextlib
import threading

import frappe
from frappe import _
from frappe.utils import get_link_to_form

from gate_pass_management.gate_pass_management.doctype.gate_pass_event_log.api import log_event
from gate_pass_management.utils.logger import get_logger, log_failure

_state = threading.local()


@contextlib.contextmanager
def cascading():
	"""Marks that a cascade is in progress, on this thread only."""
	previous = getattr(_state, "active", False)
	_state.active = True
	try:
		yield
	finally:
		_state.active = previous


def is_cascading() -> bool:
	return getattr(_state, "active", False)


def cascade_cancel(gate_pass, references):
	"""Cancel every submitted target, newest first, inside one transaction.

	Newest first because later documents usually depend on earlier ones — a
	Purchase Invoice drawn from a Purchase Receipt must go before the receipt.
	"""
	if is_cascading():
		return

	ordered = sorted(references, key=lambda r: r.created_on or "", reverse=True)

	with cascading():
		for ref in ordered:
			if not frappe.db.exists(ref.reference_doctype, ref.reference_name):
				continue
			if frappe.db.get_value(ref.reference_doctype, ref.reference_name, "docstatus") != 1:
				continue
			try:
				target = frappe.get_doc(ref.reference_doctype, ref.reference_name)
				target.flags.ignore_permissions = True
				target.cancel()
				log_event(
					gate_pass=gate_pass.name, event="Target Cancelled",
					reference_doctype=ref.reference_doctype,
					reference_name=ref.reference_name,
					message=_("Cancelled as part of cascading the Gate Pass cancellation."),
				)
			except Exception as exc:
				trace_id = log_failure(
					"cascade_cancel_failed", exc, gate_pass=gate_pass.name,
					target=ref.reference_name,
				)
				frappe.throw(
					_("Could not cancel {0}:<br><br>{1}<br><br>The Gate Pass has not been "
					  "cancelled. Reference: {2}").format(
						get_link_to_form(ref.reference_doctype, ref.reference_name),
						str(exc), trace_id,
					),
					title=_("Cascade cancellation failed"),
				)

	get_logger().info(
		"cascade_cancelled",
		extra={"gate_pass": gate_pass.name, "targets": len(ordered)},
	)
