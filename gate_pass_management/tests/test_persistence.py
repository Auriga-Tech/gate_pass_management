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
