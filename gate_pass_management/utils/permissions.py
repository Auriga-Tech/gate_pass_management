"""Row-level access to Gate Pass.

Three independent restrictions, each switchable in Settings:

  * by source type — replaces the two role names one prior implementation
    compiled into both its JS and its permission query
  * by location    — via standard User Permissions
  * by gate        — for sites where each guard owns one gate

Implemented in BOTH `permission_query_conditions` and `has_permission`, so list
views, reports and direct URL access are all covered. A filter applied only to
the list view is not an access control.
"""

from __future__ import annotations

import frappe

from gate_pass_management.utils import guards


def gate_pass_query_conditions(user: str | None = None) -> str:
	user = user or frappe.session.user
	if "Administrator" in frappe.get_roles(user):
		return ""
	if not guards.is_enabled():
		return ""

	settings = guards.get_settings()
	clauses = []

	if settings.restrict_by_source_role:
		blocked = _blocked_source_types(user)
		if blocked:
			values = ", ".join(frappe.db.escape(s) for s in blocked)
			clauses.append(
				f"(`tabGate Pass`.`source_type` IS NULL "
				f"OR `tabGate Pass`.`source_type` NOT IN ({values}))"
			)

	for enabled, field, doctype in (
		(settings.restrict_by_location, "location", "Gate Pass Location"),
		(settings.restrict_by_gate, "gate", "Gate"),
		(settings.restrict_by_company, "company", "Company"),
	):
		if not enabled:
			continue
		allowed = _user_permission_values(user, doctype)
		if allowed:
			values = ", ".join(frappe.db.escape(v) for v in allowed)
			clauses.append(
				f"(`tabGate Pass`.`{field}` IS NULL "
				f"OR `tabGate Pass`.`{field}` IN ({values}))"
			)

	return " AND ".join(clauses)


def gate_pass_has_permission(doc, ptype: str | None = None, user: str | None = None) -> bool:
	user = user or frappe.session.user
	if "Administrator" in frappe.get_roles(user):
		return True
	if not guards.is_enabled():
		return True

	settings = guards.get_settings()

	if settings.restrict_by_source_role and doc.get("source_type"):
		if doc.source_type in _blocked_source_types(user):
			return False

	for enabled, field, doctype in (
		(settings.restrict_by_location, "location", "Gate Pass Location"),
		(settings.restrict_by_gate, "gate", "Gate"),
		(settings.restrict_by_company, "company", "Company"),
	):
		if not enabled or not doc.get(field):
			continue
		allowed = _user_permission_values(user, doctype)
		if allowed and doc.get(field) not in allowed:
			return False

	return True


def _blocked_source_types(user: str) -> list[str]:
	"""Source flows this user's roles do not permit.

	A flow with no `allowed_roles` is open to everyone — the safe default, so
	turning the restriction on does not silently hide everything.
	"""
	roles = set(frappe.get_roles(user))
	blocked = []
	for source in frappe.get_all("Gate Pass Source", fields=["name"]):
		allowed = {
			r.role
			for r in frappe.get_all(
				"Gate Pass Role",
				filters={"parent": source.name, "parentfield": "allowed_roles"},
				fields=["role"],
			)
		}
		if allowed and not (allowed & roles):
			blocked.append(source.name)
	return blocked


def _user_permission_values(user: str, doctype: str) -> list[str]:
	perms = frappe.defaults.get_user_permissions(user) or {}
	entries = perms.get(doctype) or []
	return [e.get("doc") for e in entries if e.get("doc")]
