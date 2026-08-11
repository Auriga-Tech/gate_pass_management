"""Guard against workspace/DocType route collisions.

Frappe's router resolves a public workspace before a DocType route, matching on
the first path segment only and discarding the rest. A workspace sharing a slug
with a DocType therefore makes every document of that DocType unreachable by
URL — /app/gate-pass/GP-2026-00002 silently becomes the workspace dashboard.

It is a quiet failure: no error, no log line, just the wrong page. Hence a test.
"""

import frappe
from frappe.tests.utils import FrappeTestCase


def _slug(name: str) -> str:
	return frappe.scrub(name).replace("_", "-")


class TestRouting(FrappeTestCase):
	def test_workspaces_do_not_shadow_doctypes(self):
		"""No workspace this app ships may share a slug with any DocType."""
		workspaces = frappe.get_all(
			"Workspace",
			filters={"module": "Gate Pass", "public": 1},
			pluck="name",
		)
		self.assertTrue(workspaces, "expected at least one Gate Pass workspace")

		doctype_slugs = {
			_slug(d): d
			for d in frappe.get_all("DocType", filters={"module": "Gate Pass"}, pluck="name")
		}

		for workspace in workspaces:
			slug = _slug(workspace)
			shadowed = doctype_slugs.get(slug)
			self.assertIsNone(
				shadowed,
				f"Workspace {workspace!r} shadows the DocType {shadowed!r}: both resolve to "
				f"/app/{slug}. Every {shadowed} form would be unreachable by URL. "
				f"Rename the workspace — see gate_pass/workspace/README.md.",
			)

	def test_gate_pass_form_route_is_reachable(self):
		"""The slug the Gate Pass form needs is not claimed by a workspace."""
		claimed = frappe.get_all(
			"Workspace", filters={"public": 1}, pluck="name"
		)
		claimed_slugs = {_slug(w) for w in claimed}
		self.assertNotIn(
			"gate-pass",
			claimed_slugs,
			"A public workspace has claimed /app/gate-pass, which the Gate Pass "
			"DocType needs for its list and form routes.",
		)
