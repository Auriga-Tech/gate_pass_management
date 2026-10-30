"""What a gate pass looks like in the database after each lifecycle step.

Frappe writes the document and only then calls `on_submit`, `on_cancel` and
`on_update_after_submit`. A field assigned in one of those hooks is on the
Python object and nowhere else, so the form shows the old value on the next
load. Semgrep flagged exactly these assignments; every test here reads the row
back from the database rather than trusting the object in hand.
"""

import json

import frappe
from frappe.tests.utils import FrappeTestCase

from gate_pass_management.api.gate_pass import record_discrepancy
from gate_pass_management.tests.utils import ensure_masters, make_gate_pass


class TestStoredState(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.masters = ensure_masters()
		from gate_pass_management.setup import fixtures

		fixtures.seed_masters()

	def stored(self, name, *fields):
		return frappe.db.get_value("Gate Pass", name, list(fields), as_dict=True)

	def test_a_cancelled_pass_is_stored_as_cancelled(self):
		gp = make_gate_pass(self.masters, submit=True)
		self.assertNotEqual(self.stored(gp.name, "status").status, "Cancelled")

		gp.cancel()

		stored = self.stored(gp.name, "docstatus", "status")
		self.assertEqual(stored.docstatus, 2)
		self.assertEqual(stored.status, "Cancelled", "a cancelled pass must not still read Inside")

	def test_a_discrepancy_recorded_after_submit_is_stored(self):
		gp = make_gate_pass(
			self.masters, submit=True,
			rows=[{"item_name": "Free text thing", "uom": "Nos", "qty": 10, "accepted_qty": 10}],
		)
		before = self.stored(gp.name, "has_discrepancy", "total_shortage_qty", "total_accepted_qty")
		self.assertEqual(before.has_discrepancy, 0)

		row = frappe.get_doc("Gate Pass", gp.name).items[0]
		record_discrepancy(
			gp.name,
			json.dumps({row.name: {"shortage_qty": 3, "discrepancy_reason": "Short Delivered"}}),
			"counted again at unloading",
		)

		after = self.stored(
			gp.name, "has_discrepancy", "total_shortage_qty", "total_accepted_qty", "total_qty"
		)
		self.assertEqual(after.total_shortage_qty, 3)
		self.assertEqual(after.total_accepted_qty, 7, "what was accepted falls by what was short")
		self.assertEqual(after.has_discrepancy, 1)
		self.assertEqual(after.total_qty, 10, "the paperwork quantity is unchanged")


class TestRepairPatch(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.masters = ensure_masters()

	def test_it_puts_right_a_pass_cancelled_before_the_fix(self):
		from gate_pass_management.patches.v1_0.repair_stored_status_and_totals import execute

		gp = make_gate_pass(self.masters, submit=True)
		gp.cancel()
		frappe.db.set_value("Gate Pass", gp.name, "status", "Inside", update_modified=False)  # as the bug left it

		execute()

		self.assertEqual(frappe.db.get_value("Gate Pass", gp.name, "status"), "Cancelled")

	def test_it_puts_right_totals_left_stale_after_submission(self):
		from gate_pass_management.patches.v1_0.repair_stored_status_and_totals import execute

		gp = make_gate_pass(
			self.masters, submit=True,
			rows=[{"item_name": "Free text thing", "uom": "Nos", "qty": 10, "accepted_qty": 7, "shortage_qty": 3}],
		)
		frappe.db.set_value(
			"Gate Pass", gp.name, {"total_shortage_qty": 0, "has_discrepancy": 0}, update_modified=False
		)

		execute()

		stored = frappe.db.get_value("Gate Pass", gp.name, ["total_shortage_qty", "has_discrepancy"], as_dict=True)
		self.assertEqual(stored.total_shortage_qty, 3)
		self.assertEqual(stored.has_discrepancy, 1)


class TestHooksOnlyCallMethodsThatStoreWhatTheyChange(FrappeTestCase):
	"""Frappe's audit rule `frappe-modifying-but-not-committing-other-method`.

	`on_submit`, `on_cancel`, `on_update` and `on_update_after_submit` run after the
	row is written. A method they call that assigns `self.<field>` changes the object
	and nothing else, so the database keeps the old value. Such methods must return
	what they computed, and the hook stores it.
	"""

	HOOKS = ("on_submit", "on_cancel", "on_update", "on_update_after_submit")

	def test_no_helper_called_from_a_post_write_hook_assigns_a_document_field(self):
		import ast
		import pathlib

		from gate_pass_management.tests.test_wiring import MODULE_DIR, _doctype_json

		fields = {f["fieldname"] for f in _doctype_json("Gate Pass")["fields"]}
		source = (MODULE_DIR / "doctype" / "gate_pass" / "gate_pass.py").read_text(encoding="utf-8")
		cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == "GatePass")
		methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}

		def assigned_fields(fn):
			found = set()
			for node in ast.walk(fn):
				targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)] if isinstance(node, (ast.AugAssign, ast.AnnAssign)) else []
				for t in targets:
					if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self" and t.attr in fields:
						found.add(t.attr)
			return found

		problems = []
		for hook in self.HOOKS:
			if hook not in methods:
				continue
			for node in ast.walk(methods[hook]):
				if (
					isinstance(node, ast.Call)
					and isinstance(node.func, ast.Attribute)
					and isinstance(node.func.value, ast.Name)
					and node.func.value.id == "self"
					and node.func.attr in methods
					and node.func.attr not in self.HOOKS
				):
					changed = assigned_fields(methods[node.func.attr])
					if changed:
						problems.append(f"{hook} calls {node.func.attr}, which assigns {sorted(changed)}")
		self.assertEqual(problems, [], "return the values and store them with db_set in the hook")
