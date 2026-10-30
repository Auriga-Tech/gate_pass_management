"""Statutory compliance framework.

The gate is the last point at which a non-compliant dispatch is still
preventable. Once the vehicle is on the road without an E-Way Bill, the exposure
is a penalty and a detained truck. Checking at invoice creation does not work in
practice, because generation gets deferred; checking at the gate does, because
the vehicle is physically present and someone is standing next to it.

This module defines the provider contract. It is deliberately jurisdiction
neutral — India ships in the box, but the same interface serves EU customs,
Brazil NF-e, dangerous-goods declarations, or a customer's own internal release
approval. Register additional providers through the `gate_pass_compliance_providers`
hook; no fork required.

FAILURE POSTURE
---------------
Providers must never raise. A provider that cannot reach its upstream returns
PROVIDER_UNAVAILABLE, and the CMP-PROVIDER-DOWN rule decides what that means —
defaulting to Block. An app that quietly lets dispatches through whenever an API
is down is not a control.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import frappe
from frappe import _

# --- Statuses --------------------------------------------------------------

NOT_APPLICABLE = "Not Applicable"  # check does not exist for this doc/jurisdiction
NOT_REQUIRED = "Not Required"  # applies, but below threshold
PENDING = "Pending"  # required and not yet generated  -> blocks
GENERATED = "Generated"  # required and present         -> passes
FAILED = "Failed"  # generation was attempted and rejected -> blocks
PROVIDER_UNAVAILABLE = "Provider Unavailable"  # could not verify -> fails closed

PASSING_STATUSES = frozenset({NOT_APPLICABLE, NOT_REQUIRED, GENERATED})


@dataclass
class ComplianceResult:
	"""What a provider returns for one check on one document."""

	check_code: str
	status: str
	label: str = ""
	document_no: str | None = None
	document_date: str | None = None
	message: str = ""
	# Plain language, aimed at the person at the gate. "Ask the sales team to
	# generate the E-Way Bill on SI-00123" beats "einvoice_status != Generated".
	remediation: str = ""
	detail_url: str | None = None
	threshold_amount: float | None = None
	document_value: float | None = None
	# Fieldname on Gate Pass that should receive `document_no`, when the check
	# produced one. Lets a provider say "this is the E-Way Bill number" without
	# the runner knowing anything about E-Way Bills. Only an empty field is
	# filled: what the operator typed is never overwritten.
	populates: str | None = None

	@property
	def passed(self) -> bool:
		return self.status in PASSING_STATUSES

	@property
	def indicator(self) -> str:
		return {
			GENERATED: "green",
			NOT_REQUIRED: "blue",
			NOT_APPLICABLE: "gray",
			PENDING: "orange",
			FAILED: "red",
			PROVIDER_UNAVAILABLE: "red",
		}.get(self.status, "gray")


@dataclass
class ComplianceCheck:
	"""A check a provider offers, advertised so it can be configured."""

	code: str
	label: str
	description: str = ""
	applies_to_doctypes: tuple[str, ...] = ()
	supports_threshold: bool = False


class ComplianceProvider:
	"""Base class for a compliance provider.

	Subclasses implement `is_available()` and `evaluate()`. Neither may raise:
	`evaluate` is wrapped by `safe_evaluate`, but a provider that leaks
	exceptions makes the failure mode harder to diagnose for everyone.
	"""

	name: str = ""
	checks: tuple[ComplianceCheck, ...] = ()

	def is_available(self) -> bool:
		"""Whether the upstream dependency is installed and configured.

		Return False rather than raising when the app this provider integrates
		with is absent. The checks then report Not Applicable and the compliance
		section stays hidden — no half-configured state, no import errors.
		"""
		return True

	def evaluate(self, check_code: str, gate_pass, source_doc) -> ComplianceResult:
		raise NotImplementedError

	# -- wrapper used by callers ------------------------------------------

	def safe_evaluate(self, check_code: str, gate_pass, source_doc) -> ComplianceResult:
		label = self._label_for(check_code)
		if not self.is_available():
			return ComplianceResult(
				check_code=check_code,
				status=NOT_APPLICABLE,
				label=label,
				message=_("{0} is not configured on this site.").format(label),
			)
		try:
			return self.evaluate(check_code, gate_pass, source_doc)
		except Exception as exc:
			from gate_pass_management.utils.logger import get_logger

			trace_id = frappe.generate_hash(length=10)
			get_logger().error(
				"compliance_provider_error",
				extra={
					"provider": self.name,
					"check": check_code,
					"gate_pass": gate_pass.get("name"),
					"trace_id": trace_id,
					"error": str(exc),
				},
			)
			frappe.log_error(
				title=f"Gate Pass compliance provider failed: {self.name}/{check_code}",
				message=frappe.get_traceback(),
				reference_doctype="Gate Pass",
				reference_name=gate_pass.get("name"),
			)
			return ComplianceResult(
				check_code=check_code,
				status=PROVIDER_UNAVAILABLE,
				label=label,
				message=_("{0} could not be verified.").format(label),
				remediation=_("Retry, or ask a Gate Pass Manager to override. Reference: {0}").format(
					trace_id
				),
			)

	def _label_for(self, check_code: str) -> str:
		for c in self.checks:
			if c.code == check_code:
				return c.label
		return check_code


# --- Registry --------------------------------------------------------------


def get_providers() -> dict[str, ComplianceProvider]:
	"""All registered providers, keyed by check code.

	Reads the `gate_pass_compliance_providers` hook, so any installed app can
	contribute checks.
	"""
	cached = frappe.cache().get_value("gate_pass_compliance_providers")
	if cached is not None:
		# The cache stores dotted paths; instances are rebuilt per request
		# because providers may hold connections.
		pass

	registry: dict[str, ComplianceProvider] = {}
	for path in frappe.get_hooks("gate_pass_compliance_providers") or []:
		try:
			provider = frappe.get_attr(path)
		except Exception:
			frappe.log_error(
				title="Gate Pass: could not load compliance provider",
				message=f"{path}\n\n{frappe.get_traceback()}",
			)
			continue
		for check in provider.checks:
			registry[check.code] = provider
	return registry


def get_available_checks() -> list[ComplianceCheck]:
	"""Every check that can be configured, for the Select on Gate Pass Compliance Rule."""
	checks: list[ComplianceCheck] = []
	seen: set[str] = set()
	for path in frappe.get_hooks("gate_pass_compliance_providers") or []:
		try:
			provider = frappe.get_attr(path)
		except Exception:
			continue
		for check in provider.checks:
			if check.code not in seen:
				seen.add(check.code)
				checks.append(check)
	return checks
