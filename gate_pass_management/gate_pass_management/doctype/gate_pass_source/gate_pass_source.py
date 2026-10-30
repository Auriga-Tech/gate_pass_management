"""Gate Pass Source controller.

Validates the mapping against real DocType metadata on save. A misconfigured
flow should fail here, in front of the implementer who wrote it, not silently
produce empty gate passes weeks later.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document

from gate_pass_management.rules import catalogue


class GatePassSource(Document):
	def validate(self):
		self._validate_child_table()
		self._validate_fields()
		self._validate_json_fields()
		self._validate_party()
		self._validate_rule_overrides()
		self._validate_target()

	def on_update(self):
		frappe.clear_cache(doctype="Gate Pass")

	# -- mapping -----------------------------------------------------------

	def _validate_child_table(self):
		meta = frappe.get_meta(self.source_doctype)
		df = meta.get_field(self.child_table)
		if not df or df.fieldtype not in ("Table", "Table MultiSelect"):
			frappe.throw(
				_("{0} has no child table named {1}.").format(
					_(self.source_doctype), frappe.bold(self.child_table)
				)
			)
		self._child_doctype = df.options

	def _validate_fields(self):
		child_meta = frappe.get_meta(self._child_doctype)
		required = {"item_field": self.item_field, "qty_field": self.qty_field}
		optional = {
			"consumed_field": self.consumed_field,
			"uom_field": self.uom_field,
			"rate_field": self.rate_field,
			"warehouse_field": self.warehouse_field,
			"bom_field": self.bom_field,
		}

		for label, fieldname in required.items():
			if not child_meta.has_field(fieldname):
				frappe.throw(
					_("{0} has no field named {1} (set in {2}).").format(
						_(self._child_doctype), frappe.bold(fieldname), frappe.unscrub(label)
					)
				)

		for label, fieldname in optional.items():
			if fieldname and not child_meta.has_field(fieldname):
				frappe.throw(
					_("{0} has no field named {1} (set in {2}). Leave it blank if it "
					  "does not apply.").format(
						_(self._child_doctype), frappe.bold(fieldname), frappe.unscrub(label)
					)
				)

		for row in self.field_map or []:
			source_meta = (
				frappe.get_meta(self.source_doctype) if row.level == "Header" else child_meta
			)
			if not source_meta.has_field(row.source_field):
				frappe.throw(
					_("Field Mapping row {0}: {1} has no field {2}.").format(
						row.idx, source_meta.name, frappe.bold(row.source_field)
					)
				)

	def _validate_json_fields(self):
		for fieldname in ("source_filters", "party_filters", "dialog_fields"):
			value = (self.get(fieldname) or "").strip()
			if not value:
				continue
			try:
				json.loads(value)
			except ValueError as exc:
				frappe.throw(
					_("{0} is not valid JSON: {1}").format(
						frappe.bold(frappe.unscrub(fieldname)), str(exc)
					)
				)

	def _validate_party(self):
		if self.party_type == "From Field" and not self.party_field:
			frappe.throw(_("Set a Party Fieldname when Party Type is 'From Field'."))

		if self.party_field and "." not in self.party_field:
			meta = frappe.get_meta(self.source_doctype)
			if not meta.has_field(self.party_field):
				frappe.throw(
					_("{0} has no field named {1}.").format(
						_(self.source_doctype), frappe.bold(self.party_field)
					)
				)

	def _validate_rule_overrides(self):
		for row in self.rule_overrides or []:
			if row.rule_code not in catalogue.BY_CODE:
				frappe.throw(
					_("Rule Override row {0}: unknown rule code {1}.").format(
						row.idx, frappe.bold(row.rule_code)
					)
				)
			if row.rule_code not in catalogue.SOURCE_OVERRIDABLE_CODES:
				frappe.throw(
					_("Rule Override row {0}: {1} cannot be overridden per flow. It protects "
					  "data integrity rather than expressing a policy.").format(
						row.idx, frappe.bold(row.rule_code)
					)
				)

	def _validate_target(self):
		if self.target_creation_mode != "None" and not self.target_doctype:
			frappe.throw(_("Select a Target DocType, or set Creation Mode to None."))
		if self.target_mapper:
			try:
				frappe.get_attr(self.target_mapper)
			except Exception:
				frappe.throw(
					_("Custom mapper {0} could not be loaded.").format(
						frappe.bold(self.target_mapper)
					)
				)


@frappe.whitelist()
def get_compliance_check_options() -> list[dict]:
	"""Checks offered by every registered provider, for the Select field."""
	from gate_pass_management.compliance.base import get_available_checks

	return [
		{"value": c.code, "label": c.label, "description": c.description}
		for c in get_available_checks()
	]
