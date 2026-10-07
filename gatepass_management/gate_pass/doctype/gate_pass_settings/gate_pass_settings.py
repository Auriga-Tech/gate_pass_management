"""Gate Pass Settings controller."""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document

from gatepass_management.rules import catalogue


class GatePassSettings(Document):
	def validate(self):
		self._apply_preset()
		self._validate_field_rules()
		self._validate_tracking_template()
		self._apply_naming_series()

	def on_update(self):
		frappe.clear_cache(doctype="Gate Pass")

	def _apply_preset(self):
		"""Push the chosen preset onto the rule rows.

		The engine reads each row's own action before it looks at the preset, so
		without this a preset change would be recorded but never take effect.
		Custom leaves the rows as the administrator set them.
		"""
		preset = self.enforcement_preset
		if not preset or preset == catalogue.PRESET_CUSTOM:
			return
		if not self.is_new() and not self.has_value_changed("enforcement_preset"):
			return
		for row in self.rules or []:
			try:
				rule = catalogue.get(row.rule_code)
			except KeyError:
				continue
			action = catalogue.preset_action(rule, preset)
			if action in ("Block", "Warn", "Ignore"):
				row.action = action

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
