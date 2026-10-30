"""Activation guards.

Every hook this app installs on an ERPNext DocType calls `is_active()` first.
Two switches must both be satisfied before the app touches anything:

  * Gate Pass Settings.enabled — the master kill switch. When off, the app is
    inert: no validation, no blocking, no side effects. A customer who hits
    trouble mid-shift can turn it off and keep working.

  * Gate Pass Settings.enforce_from_date — the go-live date. Documents dated
    before it are governed by whatever process existed then. Making this a
    setting rather than a constant is the difference between an app anyone can
    install and one that needs a code change per customer.
"""

from __future__ import annotations

import frappe
from frappe.utils import getdate


def get_settings():
	return frappe.get_cached_doc("Gate Pass Settings")


def is_enabled() -> bool:
	try:
		return bool(frappe.get_cached_value("Gate Pass Settings", None, "enabled"))
	except Exception:
		# Settings do not exist yet (mid-install, or a fresh site being migrated).
		# Staying inert is the only safe answer.
		return False


def is_active(doc=None) -> bool:
	"""Whether gate pass rules apply to this document."""
	if not is_enabled():
		return False
	if doc is None:
		return True

	enforce_from = frappe.get_cached_value("Gate Pass Settings", None, "enforce_from_date")
	if not enforce_from:
		return True

	posting_date = (
		doc.get("posting_date")
		or doc.get("transaction_date")
		or doc.get("schedule_date")
	)
	if not posting_date:
		return True

	return getdate(posting_date) >= getdate(enforce_from)


def is_internal_party(party_type: str | None, party: str | None) -> bool:
	"""Internal transfers between the customer's own entities.

	Generalises what one prior implementation hard-coded as a supplier's legal
	name inside a SQL WHERE clause.
	"""
	if not party_type or not party:
		return False
	if party_type == "Supplier":
		return bool(frappe.db.get_value("Supplier", party, "is_internal_supplier"))
	if party_type == "Customer":
		return bool(frappe.db.get_value("Customer", party, "is_internal_customer"))
	if party_type == "Company":
		return True
	return False
