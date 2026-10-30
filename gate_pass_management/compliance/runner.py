"""Evaluates the compliance rules configured on a gate pass source."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from gate_pass_management.compliance.base import (
	NOT_APPLICABLE,
	NOT_REQUIRED,
	PENDING,
	PROVIDER_UNAVAILABLE,
	ComplianceResult,
	get_providers,
)

REQUIRED_ALWAYS = "Always"
REQUIRED_ABOVE_THRESHOLD = "Above Threshold"
REQUIRED_FROM_PROVIDER = "From Provider"
REQUIRED_NEVER = "Never"


def evaluate(gate_pass, source_config=None) -> list[ComplianceResult]:
	"""Run every compliance rule configured for this gate pass's source."""
	source_config = source_config or _get_source_config(gate_pass)
	if not source_config:
		return []

	rules = source_config.get("compliance_rules") or []
	if not rules:
		return []

	source_doc = _get_source_doc(gate_pass)
	if not source_doc:
		return []

	providers = get_providers()
	results: list[ComplianceResult] = []

	for rule in rules:
		if rule.get("required_when") == REQUIRED_NEVER:
			continue

		provider = providers.get(rule.check_code)
		if not provider:
			results.append(
				ComplianceResult(
					check_code=rule.check_code,
					status=NOT_APPLICABLE,
					label=rule.get("label") or rule.check_code,
					message=_("No provider is registered for this check."),
				)
			)
			continue

		result = provider.safe_evaluate(rule.check_code, gate_pass, source_doc)
		if rule.get("label"):
			result.label = rule.label

		result = _apply_threshold_policy(result, rule, source_doc)
		results.append(result)

	return results


def _apply_threshold_policy(result: ComplianceResult, rule, source_doc) -> ComplianceResult:
	"""Let the configured `required_when` relax a Pending result.

	A provider reports what it sees. Whether that matters is a configuration
	question, so the downgrade to Not Required happens here rather than in the
	provider.
	"""
	if result.status != PENDING:
		return result

	required_when = rule.get("required_when") or REQUIRED_FROM_PROVIDER

	if required_when == REQUIRED_ALWAYS:
		return result

	if required_when == REQUIRED_ABOVE_THRESHOLD:
		threshold = flt(rule.get("threshold_amount"))
		if rule.get("threshold_source") == "From Provider" and result.threshold_amount is not None:
			threshold = flt(result.threshold_amount)
		value = flt(
			result.document_value
			if result.document_value is not None
			else source_doc.get("base_grand_total") or source_doc.get("grand_total")
		)
		if threshold and value < threshold:
			result.status = NOT_REQUIRED
			result.message = _("Value {0} is below the configured threshold {1}.").format(
				frappe.format_value(value, {"fieldtype": "Currency"}),
				frappe.format_value(threshold, {"fieldtype": "Currency"}),
			)
			result.remediation = ""

	return result


def sync_to_gate_pass(gate_pass, results: list[ComplianceResult]):
	"""Write results onto the gate pass's child table and roll-up field."""
	gate_pass.set("compliance_checks", [])
	for r in results:
		gate_pass.append(
			"compliance_checks",
			{
				"check_code": r.check_code,
				"label": r.label,
				"status": r.status,
				"document_no": r.document_no,
				"document_date": r.document_date,
				"message": r.message,
				"remediation": r.remediation,
				"detail_url": r.detail_url,
				"document_value": r.document_value,
				"threshold_amount": r.threshold_amount,
			},
		)

	gate_pass.compliance_status = roll_up(results)
	gate_pass.compliance_checked_on = now_datetime()
	_populate_fields(gate_pass, results)


def _populate_fields(gate_pass, results: list[ComplianceResult]):
	"""Copy a check's document number onto the field the provider names.

	Fill-if-empty only. The operator may have keyed the number from the paper
	copy in the driver's hand, and silently replacing it with the system's
	value would hide exactly the discrepancy a gate check exists to catch.
	"""
	meta = frappe.get_meta("Gate Pass")
	for r in results:
		if not (r.populates and r.document_no and r.passed):
			continue
		if not meta.has_field(r.populates) or gate_pass.get(r.populates):
			continue
		gate_pass.set(r.populates, r.document_no)


def roll_up(results: list[ComplianceResult]) -> str:
	if not results:
		return "Not Applicable"
	if any(r.status == PROVIDER_UNAVAILABLE for r in results):
		return "Failed"
	if all(r.status == NOT_APPLICABLE for r in results):
		return "Not Applicable"
	if any(not r.passed for r in results):
		return "Pending"
	return "Passed"


def _get_source_config(gate_pass):
	if not gate_pass.get("source_type"):
		return None
	return frappe.get_cached_doc("Gate Pass Source", gate_pass.source_type)


def _get_source_doc(gate_pass):
	doctype = gate_pass.get("source_doctype")
	name = gate_pass.get("source_document")
	if not doctype or not name:
		# Multi-source gate passes evaluate compliance against the first source
		# document; a dispatch spanning two invoices needs both checked, so we
		# take the distinct set from the rows instead.
		rows = [r for r in (gate_pass.get("items") or []) if r.get("source_document")]
		if not rows:
			return None
		doctype = rows[0].source_doctype
		name = rows[0].source_document
	if not frappe.db.exists(doctype, name):
		return None
	return frappe.get_doc(doctype, name)
