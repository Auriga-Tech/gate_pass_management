"""Guard against route collisions with the Gate Pass DocType.

Two different things in Frappe can claim the same URL slug as a DocType, and
both fail the same quiet way — no error, no log line, just the wrong page:

1. A public **workspace**. Frappe's router resolves a workspace before a DocType
   route, matching on the first path segment only and discarding the rest, so
   /app/gate-pass/GP-2026-00002 silently becomes the workspace dashboard.

2. The **module**. Frappe builds this app's sidebar links from the module name,
   so a module called "Gate Pass" gives the prefix gate-pass and a link such as
   /desk/gate-pass/gate-pass-source resolves to a Gate Pass document named
   "gate-pass-source" and shows "not found".

Both are why the workspace and the module are called "Gate Pass Management"
while the DocType stays "Gate Pass". See gate_pass_management/workspace/README.md.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

MODULE = "Gate Pass Management"


def _slug(name: str) -> str:
	return frappe.scrub(name).replace("_", "-")


def _doctype_slugs() -> dict[str, str]:
	return {
		_slug(d): d
		for d in frappe.get_all("DocType", filters={"module": MODULE}, pluck="name")
	}


class TestRouting(FrappeTestCase):
	def test_workspaces_do_not_shadow_doctypes(self):
		"""No workspace this app ships may share a slug with any of its DocTypes."""
		workspaces = frappe.get_all(
			"Workspace",
			filters={"module": MODULE, "public": 1},
			pluck="name",
		)
		self.assertTrue(workspaces, f"expected at least one {MODULE} workspace")

		doctype_slugs = _doctype_slugs()

		for workspace in workspaces:
			slug = _slug(workspace)
			shadowed = doctype_slugs.get(slug)
			self.assertIsNone(
				shadowed,
				f"Workspace {workspace!r} shadows the DocType {shadowed!r}: both resolve to "
				f"/app/{slug}. Every {shadowed} form would be unreachable by URL. "
				f"Rename the workspace — see gate_pass_management/workspace/README.md.",
			)

	def test_module_does_not_shadow_a_doctype(self):
		"""The module name may not share a slug with any DocType it contains.

		The module name becomes the URL prefix of this app's sidebar links, so a
		collision breaks every one of them while leaving the DocType itself fine —
		which is why it is easy to miss.
		"""
		shadowed = _doctype_slugs().get(_slug(MODULE))
		self.assertIsNone(
			shadowed,
			f"Module {MODULE!r} shadows the DocType {shadowed!r}: both resolve to "
			f"/desk/{_slug(MODULE)}. Sidebar links would resolve to a {shadowed} "
			f"document instead of the intended page.",
		)

	def test_gate_pass_form_route_is_reachable(self):
		"""Nothing has claimed the slug the Gate Pass form needs."""
		claimed = {_slug(w) for w in frappe.get_all("Workspace", filters={"public": 1}, pluck="name")}
		claimed |= {_slug(m) for m in frappe.get_all("Module Def", pluck="name")}

		self.assertNotIn(
			"gate-pass",
			claimed,
			"A workspace or module has claimed /app/gate-pass, which the Gate Pass "
			"DocType needs for its list and form routes.",
		)
