"""India compliance provider — E-Invoice (IRN) and E-Way Bill.

Reads state directly from the `india_compliance` app's own fields rather than
calling the GSTN, so a gate check costs nothing and works offline:

    Sales Invoice.irn, .einvoice_status, .ewaybill
    Delivery Note.ewaybill
    Purchase Invoice.ewaybill
    Purchase Receipt.ewaybill

Thresholds come from `GST Settings` and `State Wise E Waybill Threshold`. The
statutory limit is never hard-coded here — it changes, it varies by state, and
`india_compliance` already tracks it.

Self-disables when `india_compliance` is not installed: every check reports Not
Applicable and the compliance section stays hidden. No hard dependency.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, get_link_to_form

from gatepass_management.compliance.base import (
	FAILED,
	GENERATED,
	NOT_APPLICABLE,
	NOT_REQUIRED,
	PENDING,
	ComplianceCheck,
	ComplianceProvider,
	ComplianceResult,
)

CHECK_E_INVOICE = "IN_E_INVOICE"
CHECK_E_WAY_BILL = "IN_E_WAY_BILL"

# Which doctype carries which field. Kept as data so a schema change upstream is
# a one-line fix rather than a hunt through branches.
EWAYBILL_DOCTYPES = {
	"Sales Invoice": "ewaybill",
	"Delivery Note": "ewaybill",
	"Purchase Invoice": "ewaybill",
	"Purchase Receipt": "ewaybill",
}

EINVOICE_DOCTYPES = {"Sales Invoice": "irn"}


class IndiaComplianceProvider(ComplianceProvider):
	name = "India (GST)"

	checks = (
		ComplianceCheck(
			code=CHECK_E_INVOICE,
			label=_("E-Invoice (IRN)"),
			description=_(
				"Electronic invoice registered with the IRP. Required for Sales Invoices "
				"once e-invoicing applies to the company."
			),
			applies_to_doctypes=tuple(EINVOICE_DOCTYPES),
			supports_threshold=False,
		),
		ComplianceCheck(
			code=CHECK_E_WAY_BILL,
			label=_("E-Way Bill"),
			description=_(
				"Electronic waybill required to transport goods above the state threshold."
			),
			applies_to_doctypes=tuple(EWAYBILL_DOCTYPES),
			supports_threshold=True,
		),
	)

	# -- availability ------------------------------------------------------

	def is_available(self) -> bool:
		return "india_compliance" in frappe.get_installed_apps()

	# -- evaluation --------------------------------------------------------

	def evaluate(self, check_code, gate_pass, source_doc) -> ComplianceResult:
		if check_code == CHECK_E_INVOICE:
			return self._check_e_invoice(gate_pass, source_doc)
		if check_code == CHECK_E_WAY_BILL:
			return self._check_e_way_bill(gate_pass, source_doc)
		return ComplianceResult(check_code, NOT_APPLICABLE, label=check_code)

	def _check_e_invoice(self, gate_pass, source_doc) -> ComplianceResult:
		label = _("E-Invoice (IRN)")
		doctype = source_doc.doctype if source_doc else None

		if doctype not in EINVOICE_DOCTYPES:
			return ComplianceResult(
				CHECK_E_INVOICE, NOT_APPLICABLE, label=label,
				message=_("E-Invoice does not apply to {0}.").format(_(doctype or "this document")),
			)

		gst_settings = self._gst_settings()
		if not gst_settings or not gst_settings.get("enable_e_invoice"):
			return ComplianceResult(
				CHECK_E_INVOICE, NOT_APPLICABLE, label=label,
				message=_("E-Invoicing is not enabled in GST Settings."),
			)

		status = (source_doc.get("einvoice_status") or "").strip()
		irn = (source_doc.get("irn") or "").strip()

		if status in ("Not Applicable", ""):
			# india_compliance sets Not Applicable when the company is below the
			# e-invoicing turnover threshold, or the transaction is exempt.
			if not irn and status == "Not Applicable":
				return ComplianceResult(
					CHECK_E_INVOICE, NOT_REQUIRED, label=label,
					message=_("E-Invoice is not applicable to this invoice."),
				)

		if irn:
			return ComplianceResult(
				CHECK_E_INVOICE, GENERATED, label=label, document_no=irn,
				message=_("IRN generated."),
				detail_url=self._url(source_doc),
			)

		if status in ("Failed", "Cancelled", "Pending Cancellation"):
			return ComplianceResult(
				CHECK_E_INVOICE, FAILED, label=label,
				message=_("E-Invoice status is {0}.").format(status),
				remediation=self._contact(source_doc, _("generate a fresh IRN")),
				detail_url=self._url(source_doc),
			)

		return ComplianceResult(
			CHECK_E_INVOICE, PENDING, label=label,
			message=_("IRN has not been generated for {0}.").format(source_doc.name),
			remediation=self._contact(source_doc, _("generate the E-Invoice")),
			detail_url=self._url(source_doc),
		)

	def _check_e_way_bill(self, gate_pass, source_doc) -> ComplianceResult:
		label = _("E-Way Bill")
		doctype = source_doc.doctype if source_doc else None

		if doctype not in EWAYBILL_DOCTYPES:
			return ComplianceResult(
				CHECK_E_WAY_BILL, NOT_APPLICABLE, label=label,
				message=_("E-Way Bill does not apply to {0}.").format(_(doctype or "this document")),
			)

		gst_settings = self._gst_settings()
		if not gst_settings or not gst_settings.get("enable_e_waybill"):
			return ComplianceResult(
				CHECK_E_WAY_BILL, NOT_APPLICABLE, label=label,
				message=_("E-Way Bill is not enabled in GST Settings."),
			)

		ewaybill = (source_doc.get(EWAYBILL_DOCTYPES[doctype]) or "").strip()
		value = flt(source_doc.get("base_grand_total") or source_doc.get("grand_total"))
		threshold = self._e_waybill_threshold(source_doc)

		if ewaybill:
			return ComplianceResult(
				CHECK_E_WAY_BILL, GENERATED, label=label, document_no=ewaybill,
				message=_("E-Way Bill generated."),
				document_value=value, threshold_amount=threshold,
				detail_url=self._url(source_doc),
			)

		if threshold and value < threshold:
			return ComplianceResult(
				CHECK_E_WAY_BILL, NOT_REQUIRED, label=label,
				message=_("Value {0} is below the E-Way Bill threshold {1}.").format(
					frappe.format_value(value, {"fieldtype": "Currency"}),
					frappe.format_value(threshold, {"fieldtype": "Currency"}),
				),
				document_value=value, threshold_amount=threshold,
			)

		return ComplianceResult(
			CHECK_E_WAY_BILL, PENDING, label=label,
			message=_("E-Way Bill has not been generated for {0}.").format(source_doc.name),
			remediation=self._contact(source_doc, _("generate the E-Way Bill")),
			document_value=value, threshold_amount=threshold,
			detail_url=self._url(source_doc),
		)

	# -- helpers -----------------------------------------------------------

	def _gst_settings(self):
		try:
			return frappe.get_cached_doc("GST Settings")
		except Exception:
			return None

	def _e_waybill_threshold(self, source_doc) -> float:
		"""Threshold from india_compliance's own GST Settings.

		Never hard-coded: the limit changes. GST Settings holds one national limit
		(`e_waybill_threshold`) and a table of state-wise limits that apply only to
		movement within a state (`e_waybill_threshold_for_intrastate`).
		"""
		settings = self._gst_settings()
		if not settings:
			return 0.0

		threshold = flt(settings.get("e_waybill_threshold"))

		company_gstin = source_doc.get("company_gstin") or ""
		party_gstin = source_doc.get("billing_address_gstin") or ""
		intrastate = bool(company_gstin and party_gstin and company_gstin[:2] == party_gstin[:2])
		if not intrastate:
			return threshold

		try:
			state = frappe.db.get_value("GSTIN", company_gstin, "gstin_state") or None
		except Exception:
			state = None

		for row in settings.get("e_waybill_threshold_for_intrastate") or []:
			if state and row.get("state") == state and row.get("intrastate_applicable"):
				return flt(row.get("intrastate_threshold"))

		return threshold

	def _contact(self, source_doc, action: str) -> str:
		owner = source_doc.get("owner")
		who = frappe.utils.get_fullname(owner) if owner else None
		if who:
			return _("Ask {0} (who created {1}) to {2}.").format(
				frappe.bold(frappe.utils.escape_html(who)), source_doc.name, action
			)
		return _("Ask the team that created {0} to {1}.").format(source_doc.name, action)

	def _url(self, source_doc) -> str:
		return f"/app/{frappe.scrub(source_doc.doctype).replace('_', '-')}/{source_doc.name}"


PROVIDER = IndiaComplianceProvider()
