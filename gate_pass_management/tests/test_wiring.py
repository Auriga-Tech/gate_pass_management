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

from gate_pass_management.gate_pass_management.doctype.gate_pass_settings.gate_pass_settings import (
	HIDDEN_BY_FEATURE,
)
from gate_pass_management.rules import catalogue

APP = pathlib.Path(frappe.get_app_path("gate_pass_management"))
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
			if not isinstance(path, str) or not path.startswith("gate_pass_management."):
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

		# Its own pass, so the formats are exercised on a fresh site and in CI, where
		# there is nothing already submitted to borrow.
		from gate_pass_management.tests.utils import ensure_masters, make_gate_pass

		gate_pass = make_gate_pass(ensure_masters(), submit=True)

		doc = frappe.get_doc("Gate Pass", gate_pass.name).as_json()
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
		from gate_pass_management.tests.utils import setting
		from gate_pass_management.utils.jinja import get_qr_code

		with setting(enable_qr_code=1):
			out = get_qr_code("GP-QR-TEST")
		self.assertTrue(out.startswith("data:image/png;base64,"), out[:60])


class TestSourcePickerReachesTheForm(FrappeTestCase):
	"""Get Items From pulls a document into the open draft.

	The server only returns the open pass, with the new rows merged in, when the
	form sends it back. Sent nothing, it builds a brand-new pass under a different
	name: the call succeeds, the dialog closes, and the form on screen stays empty.
	That is exactly what happened when the draft had no rows yet, and no server
	test can see it because the server answered correctly.
	"""

	def _call(self) -> str:
		js = (APP / "public" / "js" / "gate_pass.js").read_text(encoding="utf-8")
		start = js.index("api.gate_pass.build_gate_pass")
		return js[start : start + 900]

	def test_the_open_draft_is_sent_whether_or_not_it_has_rows(self):
		call = self._call()
		self.assertIn("target_doc", call)
		self.assertIn("frm.doc.docstatus === 0", call)
		self.assertNotIn(
			"items.length",
			call,
			"an empty draft must still be sent, or the pulled rows never reach the form",
		)


class TestGatePassFormLayout(FrappeTestCase):
	"""The Gate Pass form is three columns wide, with related fields together.

	A column break with nothing after it, or a fourth column, renders as a
	ragged or cramped form and nothing else would notice.
	"""

	def _sections(self):
		doc = _doctype_json("Gate Pass")
		by = {f["fieldname"]: f for f in doc["fields"]}
		sections, current = [], None
		for fieldname in doc["field_order"]:
			fieldtype = by[fieldname]["fieldtype"]
			if fieldtype == "Section Break":
				current = {"name": fieldname, "columns": [[]]}
				sections.append(current)
			elif fieldtype == "Column Break":
				current["columns"].append([])
			else:
				current["columns"][-1].append(fieldname)
		return doc, sections

	def test_every_field_is_placed_exactly_once(self):
		doc, _sections = self._sections()
		self.assertEqual(sorted(doc["field_order"]), sorted(f["fieldname"] for f in doc["fields"]))
		self.assertEqual(len(doc["field_order"]), len(set(doc["field_order"])))

	def test_no_section_has_more_than_three_columns(self):
		_doc, sections = self._sections()
		wide = [s["name"] for s in sections if len(s["columns"]) > 3]
		self.assertEqual(wide, [], "more than three columns")

	def test_no_column_is_empty(self):
		_doc, sections = self._sections()
		empty = [s["name"] for s in sections if any(not col for col in s["columns"])]
		self.assertEqual(empty, [], "a column break with nothing in it")

	def test_the_main_sections_use_all_three_columns(self):
		_doc, sections = self._sections()
		three = {s["name"] for s in sections if len(s["columns"]) == 3}
		for name in ("sb_basic", "sb_gate", "sb_source", "sb_vehicle"):
			self.assertIn(name, three, f"{name} should be laid out in three columns")

	def test_the_sections_a_feature_switch_hides_still_exist(self):
		"""Hiding is by section name, so a rename would silently stop hiding it."""
		from gate_pass_management.gate_pass_management.doctype.gate_pass_settings.gate_pass_settings import (
			HIDDEN_BY_FEATURE,
		)

		doc = _doctype_json("Gate Pass")
		names = {f["fieldname"] for f in doc["fields"]}
		missing = [f for (dt, f) in HIDDEN_BY_FEATURE if dt == "Gate Pass" and f not in names]
		self.assertEqual(missing, [])


class TestPurposeAndSourceCardAreWiredIntoTheForm(FrappeTestCase):
	"""The Purpose master's direction and default type, and the document list with
	its remove buttons, are form behaviour that no server test can see."""

	def _js(self) -> str:
		return (APP / "public" / "js" / "gate_pass.js").read_text(encoding="utf-8")

	def test_the_purpose_dropdown_is_filtered_by_direction(self):
		js = self._js()
		self.assertIn('frm.set_query("purpose"', js)
		self.assertIn("applies_to_direction", js)

	def test_picking_a_purpose_fills_in_its_default_pass_type(self):
		js = self._js()
		self.assertIn("default_gate_pass_type", js)
		self.assertIn('frm.set_value("gate_pass_type"', js)

	def test_each_document_on_a_draft_can_be_removed(self):
		js = self._js()
		self.assertIn("gatepass.unlink_source", js)
		self.assertIn("gp-src-x", js)
		self.assertIn("r.source_document !== source_document", js)

	def test_the_card_has_a_field_to_draw_into_and_the_free_text_address_is_gone(self):
		names = {f["fieldname"] for f in _doctype_json("Gate Pass")["fields"]}
		self.assertIn("source_card", names)
		self.assertNotIn("address_text", names, "an unused second free-text address field")


class TestPartyFieldsAreWiredIntoTheForm(FrappeTestCase):
	def test_address_and_contact_are_filtered_by_the_party_and_stacked_together(self):
		js = (APP / "public" / "js" / "gate_pass.js").read_text(encoding="utf-8")
		self.assertIn('frm.set_query("address"', js)
		self.assertIn('frm.set_query("contact_person"', js)
		self.assertIn("party_address_query", js)
		self.assertIn("party_contact_query", js)
		self.assertIn("clear_party_links", js)

		doc = _doctype_json("Gate Pass")
		order = doc["field_order"]
		party_column = order[order.index("cb_party") + 1 : order.index("sb_source")]
		self.assertEqual(
			party_column, ["address", "address_display", "contact_person", "contact_mobile"],
			"the contact sits under the address, in the second column",
		)

	def test_remarks_is_small_text(self):
		field = next(f for f in _doctype_json("Gate Pass")["fields"] if f["fieldname"] == "remarks")
		self.assertEqual(field["fieldtype"], "Small Text")


class TestNothingIsTranslatedAtImport(FrappeTestCase):
	"""`_()` at module or class level runs once, when the module is first imported.

	The text is then fixed in whichever language that first request used, and is
	shared by every site the process serves. Frappe's Semgrep rule
	`frappe-breaks-multitenancy` flags it. A call inside a function is fine: it
	runs per request. Module-level labels use `_lt`, which translates when read.
	"""

	def _import_time_calls(self):
		import ast

		found = []

		def visit(node, in_function, path):
			for child in ast.iter_child_nodes(node):
				inside = in_function or isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda))
				if (
					isinstance(child, ast.Call)
					and isinstance(child.func, ast.Name)
					and child.func.id == "_"
					and not in_function
				):
					found.append(f"{path}:{child.lineno}")
				visit(child, inside, path)

		for path in APP.rglob("*.py"):
			if "tests" in path.parts or "__pycache__" in path.parts:
				continue
			tree = ast.parse(path.read_text(encoding="utf-8"))
			visit(tree, False, str(path.relative_to(APP)))
		return found

	def test_no_translation_call_runs_at_import(self):
		self.assertEqual(self._import_time_calls(), [], "use _lt, or move the call into a function")


class TestVersion(FrappeTestCase):
	def test_it_is_a_release_version_and_the_install_log_reads_it(self):
		import re

		import gate_pass_management

		self.assertRegex(gate_pass_management.__version__, r"^\d+\.\d+\.\d+$", "no -dev suffix on a release")
		install = (APP / "setup" / "install.py").read_text(encoding="utf-8")
		self.assertIn("__version__", install)
		self.assertNotRegex(install, r'"version":\s*"\d', "the install log must not carry its own copy")


class TestNoUnsafePatterns(FrappeTestCase):
	"""The three things Frappe's security audit flags, kept out by construction.

	  * `render_template` on stored text (server-side template injection): this app
	    renders tracking ids with `utils.tracking` and email through Frappe's own
	    Email Template, never by handing a stored string to a template engine.
	  * an exception passed straight to `.format()`: use `str(exc)`.
	  * SQL assembled from strings: use `frappe.qb` or bound parameters.
	"""

	EXCEPTION_NAMES = {"exc", "e", "err", "error", "ex"}

	def _scan(self):
		import ast

		render, formats, sql = [], [], []
		for path in APP.rglob("*.py"):
			if "tests" in path.parts or "__pycache__" in path.parts:
				continue
			where = str(path.relative_to(APP))
			for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
				if not isinstance(node, ast.Call):
					continue
				func = node.func
				name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
				if name == "render_template":
					render.append(f"{where}:{node.lineno}")
				if name == "format" and any(
					isinstance(a, ast.Name) and a.id in self.EXCEPTION_NAMES for a in node.args
				):
					formats.append(f"{where}:{node.lineno}")
				if name in ("sql", "multisql") and node.args:
					first = node.args[0]
					built = isinstance(first, (ast.JoinedStr, ast.BinOp)) or (
						isinstance(first, ast.Call)
						and isinstance(first.func, ast.Attribute)
						and first.func.attr == "format"
					)
					if built:
						sql.append(f"{where}:{node.lineno}")
		return render, formats, sql

	def test_nothing_renders_stored_text_as_a_template(self):
		self.assertEqual(self._scan()[0], [], "use utils.tracking, or Frappe's Email Template")

	def test_no_exception_is_formatted_into_a_message_directly(self):
		self.assertEqual(self._scan()[1], [], "pass str(exc), not exc")

	def test_no_sql_is_built_from_strings(self):
		self.assertEqual(self._scan()[2], [], "use frappe.qb or bound parameters")
