"""Gate Pass Settings controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from gate_pass_management.rules import catalogue
from gate_pass_management.utils import tracking

# section/field                       : the setting that must be on for it to show
HIDDEN_BY_FEATURE = {
	("Gate Pass", "sb_discrepancy"): "enable_discrepancy",
	("Gate Pass Item", "sb_disc"): "enable_discrepancy",
	("Gate Pass Item", "sb_disc2"): "enable_discrepancy",
	("Gate Pass", "sb_charges"): "enable_charges",
	("Gate Pass", "sb_weight"): "enable_weighbridge",
	("Gate Pass", "sb_returnable"): "enable_returnable",
	("Gate Pass", "sb_compliance"): "enable_compliance_checks",
	("Gate Pass", "cost_center"): "enable_cost_center",
	("Gate Pass", "security_officer"): "enable_security_officer",
	("Gate Pass", "eway_bill_no"): "enable_eway_bill",
	("Gate Pass", "total_amount"): "enable_valuation",
	("Gate Pass Item", "sb_value"): "enable_valuation",
	("Gate Pass Item", "packages"): "enable_packages",
	("Gate Pass", "total_packages"): "enable_packages",
	("Gate Pass Item", "batch_no"): "enable_batch_serial",
	("Gate Pass Item", "serial_no"): "enable_batch_serial",
}


class GatePassSettings(Document):
	def validate(self):
		self._validate_field_rules()
		self._validate_default_party_type()
		self._validate_tracking_template()
		self._apply_naming_series()
		self._apply_feature_visibility()

	def on_update(self):
		frappe.clear_cache(doctype="Gate Pass")

	def _validate_field_rules(self):
		"""Catch a typo at configuration time rather than at 2 a.m. at the gate."""
		for rule in self.field_rules or []:
			meta = frappe.get_meta(rule.document)
			if not meta.has_field(rule.fieldname):
				frappe.throw(
					_("Row {0}: {1} has no field named {2}.").format(
						rule.idx, _(rule.document), frappe.bold(rule.fieldname)
					)
				)

	def _validate_default_party_type(self):
		"""A default that the allowed list then refuses would fail every new pass."""
		allowed = [r.party_type for r in self.allowed_party_types or [] if r.party_type]
		if self.default_party_type and allowed and self.default_party_type not in allowed:
			frappe.throw(
				_("Default Party Type {0} is not in Allowed Party Types. Add it there, or choose "
				  "another default.").format(frappe.bold(self.default_party_type)),
				title=_("Default Party Type not allowed"),
			)

	def _validate_tracking_template(self):
		if not self.enable_tracking_id or not self.tracking_id_template:
			return
		try:
			tracking.check(self.tracking_id_template)
		except ValueError as exc:
			frappe.throw(
				_("Tracking ID template is not valid: {0}").format(str(exc)),
				title=_("Check the template"),
			)

	def _apply_naming_series(self):
		"""Push the configured series onto the Gate Pass field."""
		series = []
		if self.separate_series_by_direction:
			series = [s for s in (self.naming_series_in, self.naming_series_out) if s]
		else:
			series = [
				s.strip() for s in (self.naming_series or "").splitlines() if s.strip()
			]
		if not series:
			return

		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		make_property_setter(
			"Gate Pass", "naming_series", "options", "\n".join(series), "Text",
			validate_fields_for_doctype=False,
		)

	def _apply_feature_visibility(self):
		"""Hide the sections a disabled feature owns.

		Several Features switches only ever gated validation, so turning one off
		left its fields on the form with nothing behind them — the operator still
		saw a Discrepancy section on a flow where discrepancies were switched
		off. A Property Setter is used rather than `depends_on` because these are
		site-wide decisions, not per-document ones, and the field should not
		reappear when some other value on the form changes.

		The map lives at module level so test_wiring can check that every name
		in it is real: a setting that does not exist reads as None here, which
		hides the field on every site with no way to bring it back.
		"""
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		for (doctype, fieldname), setting in HIDDEN_BY_FEATURE.items():
			make_property_setter(
				doctype, fieldname, "hidden", 0 if self.get(setting) else 1, "Check",
				validate_fields_for_doctype=False,
			)


@frappe.whitelist()
def get_rule_summary() -> dict:
	"""Counts for the Settings dashboard: how much is actually being enforced."""
	settings = frappe.get_single("Gate Pass Settings")
	counts = {"Block": 0, "Warn": 0, "Ignore": 0}
	for row in settings.rules or []:
		if row.action in counts:
			counts[row.action] += 1
	counts["Hard"] = len([r for r in catalogue.ALL_RULES if r.is_hard])
	return counts
