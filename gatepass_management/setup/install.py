"""Install and migrate hooks.

Everything here is idempotent. `after_migrate` runs on every `bench migrate`, so
it must converge rather than duplicate — and it must never overwrite a decision
a customer has made.

The reconciliation rule for rules and standard sources: ADD what is new, REMOVE
what the product has retired, LEAVE ALONE anything the customer has touched.
"""

from __future__ import annotations

import frappe
from frappe import _

from gatepass_management.rules import catalogue
from gatepass_management.setup import fixtures
from gatepass_management.utils.logger import get_logger


def after_install():
	create_roles()
	create_custom_fields()
	seed_settings()
	reconcile_rules()
	fixtures.seed_sources()
	fixtures.seed_masters()
	frappe.db.commit()
	get_logger().info("app_installed", extra={"version": "1.0.0-dev"})


def after_migrate():
	create_roles()
	create_custom_fields()
	seed_settings()
	reconcile_rules()
	fixtures.seed_sources()
	# Only when the table is empty. Sites that installed before these masters
	# existed still get them; a site that deliberately deleted one does not get
	# it back on every migrate.
	if not frappe.db.count("Gate Pass Discrepancy Reason"):
		fixtures.seed_masters()


def before_uninstall():
	"""Remove what this app owns, leave the customer's data alone.

	Custom fields and property setters are ours to clean up. Gate Pass documents
	are the customer's records and are deliberately left in place.
	"""
	delete_custom_fields()


# ---------------------------------------------------------------- roles

ROLES = [
	("Gate Pass Operator", _("Security staff at the gate. Creates and submits gate passes.")),
	("Gate Pass User", _("Stores and purchase staff. Creates gate passes and target documents.")),
	("Gate Pass Manager", _("Cancels, amends, and may override rules where configured.")),
	("Gate Pass Auditor", _("Read-only access, including the full event log.")),
]


def create_roles():
	for name, description in ROLES:
		if frappe.db.exists("Role", name):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": name,
				"desk_access": 1,
				"description": description,
			}
		).insert(ignore_permissions=True)


# -------------------------------------------------------- custom fields


def create_custom_fields():
	from frappe.custom.doctype.custom_field.custom_field import create_custom_fields as _create

	_create(fixtures.CUSTOM_FIELDS, ignore_validate=True, update=True)


def delete_custom_fields():
	for doctype, fields in fixtures.CUSTOM_FIELDS.items():
		for field in fields:
			name = f"{doctype}-{field['fieldname']}"
			if frappe.db.exists("Custom Field", name):
				frappe.delete_doc("Custom Field", name, ignore_permissions=True, force=True)


# ------------------------------------------------------------- settings


# Features switches added after 1.0.0. A Single that was saved before the field
# existed has no value for it, which reads as off — and an off Features switch
# hides its field, so the operator would be left with no way to bring it back.
# Only a field that has never been stored is seeded; a deliberate 0 is a
# customer decision and stays.
NEW_FEATURE_DEFAULTS = {
	"enable_security_officer": 1,
	"enable_eway_bill": 1,
}


def seed_settings():
	settings = frappe.get_single("Gate Pass Settings")

	stored = frappe.db.get_singles_dict("Gate Pass Settings")
	for fieldname, default in NEW_FEATURE_DEFAULTS.items():
		if stored.get(fieldname) is None:
			settings.set(fieldname, default)

	if not settings.get("allowed_party_types"):
		for party_type in ("Supplier", "Customer", "Company"):
			settings.append("allowed_party_types", {"party_type": party_type})

	if not settings.get("charge_types"):
		for charge in ("Transportation", "Packaging", "Local Freight", "Loading / Unloading"):
			settings.append("charge_types", {"charge_type": charge, "is_active": 1})

	if not settings.get("timestamp_edit_roles"):
		settings.append("timestamp_edit_roles", {"role": "Gate Pass Manager"})
	if not settings.get("attachment_unlock_roles"):
		settings.append("attachment_unlock_roles", {"role": "Gate Pass Manager"})
	if not settings.get("compliance_override_roles"):
		settings.append("compliance_override_roles", {"role": "Gate Pass Manager"})
	if not settings.get("post_submit_discrepancy_roles"):
		settings.append("post_submit_discrepancy_roles", {"role": "Gate Pass Manager"})
		settings.append("post_submit_discrepancy_roles", {"role": "Gate Pass User"})

	settings.flags.ignore_permissions = True
	settings.flags.ignore_mandatory = True
	settings.save(ignore_permissions=True)


def reconcile_rules():
	"""Sync the rule table against the catalogue.

	New rules in a future version appear at their default action. Retired rules
	are dropped. Existing rows keep whatever the customer set — their
	configuration is never silently reverted by an upgrade.
	"""
	settings = frappe.get_single("Gate Pass Settings")
	preset = settings.get("enforcement_preset") or catalogue.PRESET_ADVISORY

	existing = {row.rule_code: row for row in settings.get("rules") or []}
	valid_codes = {r.code for r in catalogue.CONFIGURABLE_RULES}

	added = 0
	for rule in catalogue.CONFIGURABLE_RULES:
		row = existing.get(rule.code)
		if row:
			# Refresh the descriptive columns only; never touch `action`,
			# `threshold`, `bypass_roles` or `require_override_reason`.
			row.rule_name = rule.label
			row.category = rule.category
			row.description = rule.description
			row.default_action = rule.default_action
			row.can_ignore = 1 if rule.can_ignore else 0
			continue

		settings.append(
			"rules",
			{
				"rule_code": rule.code,
				"rule_name": rule.label,
				"category": rule.category,
				"description": rule.description,
				"action": catalogue.preset_action(rule, preset),
				"default_action": rule.default_action,
				"can_ignore": 1 if rule.can_ignore else 0,
				"threshold": rule.default_threshold or None,
				"require_override_reason": 1 if rule.always_block else 0,
			},
		)
		added += 1

	retired = [row for row in settings.get("rules") or [] if row.rule_code not in valid_codes]
	for row in retired:
		settings.remove(row)

	if added or retired:
		settings.flags.ignore_permissions = True
		settings.flags.ignore_mandatory = True
		settings.save(ignore_permissions=True)
		get_logger().info(
			"rules_reconciled", extra={"added": added, "retired": len(retired), "preset": preset}
		)


@frappe.whitelist()
def apply_preset(preset: str):
	"""Rewrite every rule row to match a preset.

	Called from the Settings form when the preset is changed. Statutory rules
	stay at Block regardless — see catalogue.preset_action.
	"""
	frappe.only_for(("Gate Pass Manager", "System Manager"))
	if preset not in catalogue.PRESETS:
		frappe.throw(_("Unknown preset: {0}").format(preset))
	if preset == catalogue.PRESET_CUSTOM:
		return

	settings = frappe.get_single("Gate Pass Settings")
	for row in settings.get("rules") or []:
		try:
			rule = catalogue.get(row.rule_code)
		except KeyError:
			continue
		row.action = catalogue.preset_action(rule, preset)

	settings.enforcement_preset = preset
	settings.flags.ignore_permissions = True
	settings.save(ignore_permissions=True)
	frappe.msgprint(
		_("All rules set to the {0} preset.").format(frappe.bold(preset)), alert=True
	)
