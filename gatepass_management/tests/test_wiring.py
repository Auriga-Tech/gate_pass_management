"""Guard against the failure this app keeps repeating.

Every defect found in the last two audits was the same shape: something was
specified, a field or an endpoint was created for it, and the wiring was never
finished. A Settings switch nothing read. A rule that could be set and was never
evaluated. A client script registered in hooks.py that did not exist. A
dashboard counting a column that was not there.

None of those break a test that exercises behaviour, because there is no
behaviour — that is exactly why they survived. They are caught by asking the
codebase about itself, which is what this module does.

If one of these fails, do not delete the field or the assertion. Either finish
the wiring, or remove the thing that promises it.
"""

import json
import pathlib
import re

import frappe
from frappe.tests.utils import FrappeTestCase

from gatepass_management.gate_pass_management.doctype.gate_pass_settings.gate_pass_settings import (
	HIDDEN_BY_FEATURE,
)
from gatepass_management.rules import catalogue

APP = pathlib.Path(frappe.get_app_path("gatepass_management"))
MODULE_DIR = APP / "gate_pass_management"

# Fieldtypes that only arrange a form and so cannot be "read" by code.
LAYOUT_FIELDS = {"Section Break", "Column Break", "Tab Break", "HTML", "Heading"}


def _source_text() -> str:
	"""Every line of Python and JavaScript this app ships."""
	parts = []
	for pattern in ("**/*.py", "**/*.js"):
		for path in APP.rglob(pattern):
			if "__pycache__" in str(path) or "/dist/" in str(path):
				continue
			parts.append(path.read_text(encoding="utf-8"))
	return "\n".join(parts)


def _doctype_json(name: str) -> dict:
	scrub = frappe.scrub(name)
	return json.loads((MODULE_DIR / "doctype" / scrub / f"{scrub}.json").read_text())


class TestSettingsAreWired(FrappeTestCase):
	def test_every_setting_is_read_somewhere(self):
		"""A switch nobody reads is a promise the app does not keep.

		Twenty-one of sixty-seven settings were dead when this was first checked,
		including several the User Manual told people to use.
		"""
		meta = _doctype_json("Gate Pass Settings")
		code = _source_text()

		dead = [
			f["fieldname"]
			for f in meta["fields"]
			if f["fieldtype"] not in LAYOUT_FIELDS
			and not re.search(rf"\b{re.escape(f['fieldname'])}\b", code)
		]

		self.assertEqual(
			dead,
			[],
			"These Gate Pass Settings fields are never read by any code:\n  "
			+ "\n  ".join(dead)
			+ "\n\nWire them up, or remove them so the page stops promising them.",
		)


class TestFeatureVisibilityIsWired(FrappeTestCase):
	"""The Features switches that hide form fields must name real things.

	`_apply_feature_visibility` reads `self.get(setting)`, so a setting that is
	not a field on Gate Pass Settings reads as None and the field it guards is
	hidden on every install with nothing to turn it back on. Security Officer
	and E-Way Bill No were invisible this way from the first install.
	"""

	def test_every_feature_setting_exists_on_settings(self):
		known = {
			f["fieldname"] for f in _doctype_json("Gate Pass Settings")["fields"]
		}
		missing = sorted({s for s in HIDDEN_BY_FEATURE.values() if s not in known})
		self.assertEqual(
			missing,
			[],
			"HIDDEN_BY_FEATURE names settings that are not fields on Gate Pass "
			"Settings, so the fields they guard are always hidden:\n  "
			+ "\n  ".join(missing),
		)

	def test_every_guarded_field_exists(self):
		missing = [
			f"{doctype}.{fieldname}"
			for doctype, fieldname in HIDDEN_BY_FEATURE
			if not frappe.get_meta(doctype).has_field(fieldname)
		]
		self.assertEqual(
			missing,
			[],
			"HIDDEN_BY_FEATURE guards fields that do not exist, so the Property "
			"Setter is written against nothing:\n  " + "\n  ".join(missing),
		)


class TestRulesAreWired(FrappeTestCase):
	def test_every_configurable_rule_is_evaluated(self):
		"""A rule the user can set to Block must be capable of blocking.

		Five rules shipped with Block/Warn/Ignore dropdowns that changed nothing.
		"""
		code = _source_text()
		referenced = set()
		for pattern in (
			r'ctx\.check\(\s*\n?\s*"([A-Z0-9-]+)"',
			r'ctx\.is_active\(\s*"([A-Z0-9-]+)"',
			r'ctx\.threshold\(\s*"([A-Z0-9-]+)"',
			r'resolve_action\(\s*"([A-Z0-9-]+)"',
			r'"([A-Z]{3,4}-[A-Z0-9-]+)"',
		):
			referenced |= set(re.findall(pattern, code))

		dead = sorted(r.code for r in catalogue.CONFIGURABLE_RULES if r.code not in referenced)
		self.assertEqual(
			dead,
			[],
			"These rules appear in Gate Pass Settings but are never evaluated:\n  "
			+ "\n  ".join(dead),
		)

	def test_hard_rules_are_not_offered_as_settings(self):
		"""A rule that always blocks must not appear as a dropdown."""
		configurable = {r.code for r in catalogue.CONFIGURABLE_RULES}
		hard = {r.code for r in catalogue.ALL_RULES if r.is_hard}
		self.assertEqual(
			configurable & hard, set(), "a HARD rule is being offered as configurable"
		)

	def test_presets_resolve_for_every_rule(self):
		for preset in catalogue.PRESETS:
			if preset == catalogue.PRESET_CUSTOM:
				continue
			for rule in catalogue.ALL_RULES:
				action = catalogue.preset_action(rule, preset)
				self.assertIn(
					action,
					(*catalogue.ACTIONS, catalogue.HARD),
					f"{rule.code} resolved to {action!r} under {preset}",
				)

	def test_statutory_rules_block_under_every_preset(self):
		"""Advisory describes our own process maturity, not permission to
		dispatch without an E-Way Bill."""
		for rule in catalogue.ALL_RULES:
			if not rule.always_block:
				continue
			for preset in catalogue.PRESETS:
				if preset == catalogue.PRESET_CUSTOM:
					continue
				self.assertEqual(
					catalogue.preset_action(rule, preset),
					catalogue.BLOCK,
					f"{rule.code} stopped blocking under {preset}",
				)


class TestHooksResolve(FrappeTestCase):
	def test_every_client_script_exists(self):
		"""Frappe ignores a missing doctype_js file in silence.

		Eight of the nine registered scripts did not exist, which is why
		"Create -> Gate Pass" was missing from every source document while the
		README described it.
		"""
		# This app's own hooks.py, not frappe.get_hooks: that merges every
		# installed app, and ERPNext's script paths are not ours to resolve.
		source = (APP / "hooks.py").read_text()
		missing = []

		for hook in ("doctype_js", "doctype_list_js"):
			# Non-greedy to the first closing brace: these dicts have no nested
			# braces, and anchoring on a line-start "}" misses the single-line one.
			block = re.search(rf"^{hook}\s*=\s*\{{(.*?)\}}", source, re.S | re.M)
			if not block:
				continue
			for doctype, rel in re.findall(r'"([^"]+)"\s*:\s*"([^"]+)"', block.group(1)):
				if not (APP / rel).exists():
					missing.append(f"{hook}: {doctype} -> {rel}")

		self.assertEqual(
			missing,
			[],
			"client scripts registered in hooks.py that do not exist:\n  " + "\n  ".join(missing),
		)

	def test_every_python_hook_resolves(self):
		"""A dotted path in hooks.py that does not import fails only when the
		event fires, which may be months later and on a customer's site."""
		bad = []

		def check(path):
			if not isinstance(path, str) or not path.startswith("gatepass_management."):
				return
			try:
				frappe.get_attr(path)
			except Exception as exc:
				bad.append(f"{path} -> {type(exc).__name__}: {exc}")

		for hook in (
			"doc_events",
			"scheduler_events",
			"override_doctype_dashboards",
			"permission_query_conditions",
			"has_permission",
			"gate_pass_compliance_providers",
			"after_install",
			"after_migrate",
			"before_uninstall",
		):
			value = frappe.get_hooks(hook)
			stack = [value]
			while stack:
				item = stack.pop()
				if isinstance(item, dict):
					stack.extend(item.values())
				elif isinstance(item, (list, tuple)):
					stack.extend(item)
				else:
					check(item)

		self.assertEqual(bad, [], "hooks that do not resolve:\n  " + "\n  ".join(bad))


class TestPrintFormatsRender(FrappeTestCase):
	def test_shipped_print_formats_render(self):
		"""A print format that raises is discovered by a guard at the gate."""
		from frappe.www.printview import get_html_and_style

		gate_pass = frappe.get_all("Gate Pass", filters={"docstatus": 1}, limit=1, pluck="name")
		if not gate_pass:
			self.skipTest("no submitted Gate Pass on this site")

		doc = frappe.get_doc("Gate Pass", gate_pass[0]).as_json()
		for pf in frappe.get_all(
			"Print Format", filters={"doc_type": "Gate Pass", "standard": "Yes"}, pluck="name"
		):
			with self.subTest(print_format=pf):
				html = get_html_and_style(doc=doc, print_format=pf, no_letterhead=1)["html"]
				self.assertGreater(len(html), 200, f"{pf} rendered almost nothing")


class TestReportsRun(FrappeTestCase):
	def test_every_shipped_report_runs(self):
		"""Each report, with the filters its own JS marks as required."""
		from frappe.desk.query_report import run

		today = frappe.utils.today()
		base = {
			"from_date": frappe.utils.add_months(today, -3),
			"to_date": today,
			"days": 30,
			"preset": "Balanced",
		}

		for name in frappe.get_all(
			"Report", filters={"module": "Gate Pass Management", "is_standard": "Yes"}, pluck="name"
		):
			with self.subTest(report=name):
				result = run(name, filters=base, ignore_prepared_report=True)
				self.assertIsNotNone(result.get("columns"), f"{name} returned no columns")


class TestDeclaredDependencies(FrappeTestCase):
	def test_the_qr_libraries_are_declared(self):
		"""`utils.jinja` imports these directly. They arrive today through Frappe
		and ERPNext, which is exactly the kind of dependency that disappears
		without anyone touching this app."""
		try:
			import tomllib
		except ImportError:
			self.skipTest("tomllib needs Python 3.11")

		pyproject = APP.parent / "pyproject.toml"
		declared = {
			re.split(r"[~=<>!\s]", dep, maxsplit=1)[0].lower()
			for dep in tomllib.loads(pyproject.read_text())["project"]["dependencies"]
		}
		self.assertTrue(
			{"pyqrcode", "pypng"} <= declared, f"pyproject.toml declares {sorted(declared)}"
		)

	def test_a_qr_code_is_actually_produced(self):
		from gatepass_management.tests.utils import setting
		from gatepass_management.utils.jinja import get_qr_code

		with setting(enable_qr_code=1):
			out = get_qr_code("GP-QR-TEST")
		self.assertTrue(out.startswith("data:image/png;base64,"), out[:60])
