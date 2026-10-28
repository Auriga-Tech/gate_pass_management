"""Gate Pass Settings controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from gatepass_management.rules import catalogue


class GatePassSettings(Document):
	def validate(self):
		self._validate_field_rules()
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

	def _validate_tracking_template(self):
		if not self.enable_tracking_id or not self.tracking_id_template:
			return
		try:
			frappe.render_template(
				self.tracking_id_template,
				{
					"party_code": "TEST", "party": "TEST", "reference_no": "TEST",
					"vehicle_number": "TEST", "posting_date": "2026-01-01", "direction": "In",
				},
			)
		except Exception as exc:
			frappe.throw(
				_("Tracking ID template is not valid: {0}").format(exc),
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
		"""
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		hidden_by_feature = {
			# section/field            : the setting that must be on for it to show
			("Gate Pass", "sb_discrepancy"): "enable_discrepancy",
			("Gate Pass Item", "sb_disc"): "enable_discrepancy",
			("Gate Pass Item", "sb_disc2"): "enable_discrepancy",
			("Gate Pass", "sb_charges"): "enable_charges",
			("Gate Pass", "sb_weight"): "enable_weighbridge",
			("Gate Pass", "sb_returnable"): "enable_returnable",
			("Gate Pass", "sb_compliance"): "enable_compliance_checks",
		}

		for (doctype, fieldname), setting in hidden_by_feature.items():
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
