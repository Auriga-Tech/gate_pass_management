"""The status engine.

`derive_status` and `derive_return_status` are pure, so they are tested as a
table of inputs with no database at all. That matters because status is what the
Pending Gate Passes worklist and the overdue scheduler read: a wrong answer here
sends people to the wrong yard, or hides material that has not come back.

This caught a real bug once already — `per_processed` was measured against the
paperwork quantity, so any pass with a shortage could never reach 100% and sat
on the worklist for ever.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from gate_pass_management.gate_pass_management.doctype.gate_pass.gate_pass import (
	compute_per_processed,
	derive_return_status,
	derive_status,
)

YESTERDAY = add_days(today(), -1)
TOMORROW = add_days(today(), 1)


def pass_doc(**fields):
	"""A plain object with the fields the status functions read."""
	base = {
		"docstatus": 1,
		"direction": "In",
		"entry_datetime": None,
		"exit_datetime": None,
		"per_processed": 0,
		"total_qty": 0,
		"total_accepted_qty": 0,
		"returned_qty": 0,
		"is_returnable": 0,
		"expected_return_date": None,
		"source_type": None,
	}
	base.update(fields)
	return frappe._dict(base)


class TestPerProcessed(FrappeTestCase):
	def test_measured_against_accepted_not_paperwork(self):
		"""The bug this function was extracted to fix.

		A pass of 100 where 6 were damaged accepts 94. Once those 94 are
		received the pass is finished, and must read 100% — measured against
		the paperwork it would read 94% and never leave the worklist.
		"""
		self.assertEqual(compute_per_processed(94, 94), 100)

	def test_zero_accepted_is_not_a_division_error(self):
		self.assertEqual(compute_per_processed(0, 0), 0)

	def test_partial(self):
		self.assertEqual(compute_per_processed(42, 84), 50)


class TestDeriveStatus(FrappeTestCase):
	def test_draft_and_cancelled_ignore_everything_else(self):
		self.assertEqual(derive_status(pass_doc(docstatus=0, per_processed=100)), "Draft")
		self.assertEqual(derive_status(pass_doc(docstatus=2, per_processed=100)), "Cancelled")

	def test_inward_progression(self):
		cases = [
			({"entry_datetime": None}, "At Gate"),
			({"entry_datetime": "2026-01-01 10:00:00", "per_processed": 0}, "Inside"),
			({"entry_datetime": "2026-01-01 10:00:00", "per_processed": 40}, "Partially Processed"),
			({"entry_datetime": "2026-01-01 10:00:00", "per_processed": 100}, "Completed"),
		]
		for fields, expected in cases:
			with self.subTest(**fields):
				self.assertEqual(derive_status(pass_doc(direction="In", **fields)), expected)

	def test_outward_without_exit_is_still_at_the_gate(self):
		self.assertEqual(derive_status(pass_doc(direction="Out")), "At Gate")

	def test_outward_not_returnable_completes(self):
		doc = pass_doc(direction="Out", exit_datetime="2026-01-01 10:00:00")
		self.assertEqual(derive_status(doc), "Completed")

	def test_returnable_progression(self):
		out = {"direction": "Out", "exit_datetime": "2026-01-01 10:00:00", "is_returnable": 1}
		cases = [
			({"total_qty": 10, "returned_qty": 0, "expected_return_date": TOMORROW}, "Pending Return"),
			({"total_qty": 10, "returned_qty": 0, "expected_return_date": YESTERDAY}, "Overdue Return"),
			({"total_qty": 10, "returned_qty": 4, "expected_return_date": TOMORROW}, "Partially Returned"),
			({"total_qty": 10, "returned_qty": 10, "expected_return_date": TOMORROW}, "Returned"),
		]
		for fields, expected in cases:
			with self.subTest(**fields):
				self.assertEqual(derive_status(pass_doc(**out, **fields)), expected)

	def test_returned_in_full_beats_an_overdue_date(self):
		"""Everything is back. The date it was due no longer matters."""
		doc = pass_doc(
			direction="Out", exit_datetime="2026-01-01 10:00:00", is_returnable=1,
			total_qty=10, returned_qty=10, expected_return_date=YESTERDAY,
		)
		self.assertEqual(derive_status(doc), "Returned")

	def test_no_due_date_never_becomes_overdue(self):
		"""Why `_default_return_date` exists.

		The scheduler selects on expected_return_date < today and a NULL never
		matches, so a returnable pass saved without a date would never be chased.
		"""
		doc = pass_doc(
			direction="Out", exit_datetime="2026-01-01 10:00:00", is_returnable=1,
			total_qty=10, returned_qty=0, expected_return_date=None,
		)
		self.assertEqual(derive_status(doc), "Pending Return")


class TestDeriveReturnStatus(FrappeTestCase):
	def test_not_applicable_unless_outward_and_returnable(self):
		self.assertEqual(derive_return_status(pass_doc(direction="In", is_returnable=1)), "Not Applicable")
		self.assertEqual(derive_return_status(pass_doc(direction="Out", is_returnable=0)), "Not Applicable")

	def test_states(self):
		out = {"direction": "Out", "is_returnable": 1}
		cases = [
			({"total_qty": 10, "returned_qty": 0, "expected_return_date": TOMORROW}, "Pending"),
			({"total_qty": 10, "returned_qty": 0, "expected_return_date": YESTERDAY}, "Overdue"),
			({"total_qty": 10, "returned_qty": 3}, "Partially Returned"),
			({"total_qty": 10, "returned_qty": 10}, "Returned"),
			({"total_qty": 10, "returned_qty": 11}, "Returned"),
		]
		for fields, expected in cases:
			with self.subTest(**fields):
				self.assertEqual(derive_return_status(pass_doc(**out, **fields)), expected)

	def test_agrees_with_derive_status(self):
		"""The two are read side by side on the list view and the report, so
		they must never tell different stories."""
		out = {"direction": "Out", "exit_datetime": "2026-01-01 10:00:00", "is_returnable": 1}
		mapping = {
			"Returned": "Returned",
			"Partially Returned": "Partially Returned",
			"Overdue": "Overdue Return",
			"Pending": "Pending Return",
		}
		for returned, due in ((0, TOMORROW), (0, YESTERDAY), (4, TOMORROW), (10, TOMORROW)):
			doc = pass_doc(**out, total_qty=10, returned_qty=returned, expected_return_date=due)
			with self.subTest(returned=returned, due=due):
				self.assertEqual(derive_status(doc), mapping[derive_return_status(doc)])
