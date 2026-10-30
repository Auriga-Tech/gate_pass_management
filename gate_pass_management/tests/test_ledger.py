"""The consumption ledger.

The central mechanism of the app and, until now, the one with no test at all.
Everything here was previously verified by running a script by hand and reading
the output, which protects nothing once the script is gone.

What has to hold:

  * a partial pass leaves the rest of the line available, and only that line
  * quantity is tracked per source ROW, so the same item on two order lines
    cannot borrow from itself
  * only submitted passes count; a draft or a cancelled one does not
  * the lock-taking read and the display read agree
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from gate_pass_management import ledger
from gate_pass_management.tests.utils import (
	ITEM,
	ITEM_B,
	ensure_masters,
	gate_pass_from_source,
	make_purchase_order,
	source_name_for,
)


class LedgerTest(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.masters = ensure_masters()
		cls.flow = source_name_for("Purchase Order", "In")

	def pending(self, po) -> dict:
		"""Pending qty keyed by item code, which reads better in an assertion."""
		config = frappe.get_cached_doc("Gate Pass Source", self.flow)
		by_row = ledger.pending_qty("Purchase Order", po.name, config)
		return {
			frappe.db.get_value("Purchase Order Item", row, "item_code"): info["pending"]
			for row, info in by_row.items()
		}

	def pass_for(self, po, quantities: dict, submit=True):
		"""A gate pass against `po` taking the given qty per item code."""
		gp = gate_pass_from_source(self.flow, po.name)
		keep = []
		for row in gp.items:
			if row.item_code in quantities:
				row.qty = quantities[row.item_code]
				row.accepted_qty = quantities[row.item_code]
				keep.append(row)
		gp.set("items", keep)
		gp.vehicle_number = "GP-TEST-0002"
		gp.driver_name = "Test Driver"
		gp.flags.ignore_permissions = True
		gp.insert(ignore_permissions=True)
		if submit:
			gp.submit()
		return gp


class TestConsumption(LedgerTest):
	def test_a_fresh_order_is_fully_pending(self):
		po = make_purchase_order(self.masters, [(ITEM, 100), (ITEM_B, 50)])
		self.assertEqual(self.pending(po), {ITEM: 100, ITEM_B: 50})

	def test_a_partial_pass_consumes_only_its_own_line(self):
		"""The chaining case. 60 of one item leaves 40 there and the other
		line untouched."""
		po = make_purchase_order(self.masters, [(ITEM, 100), (ITEM_B, 50)])
		self.pass_for(po, {ITEM: 60})
		self.assertEqual(self.pending(po), {ITEM: 40, ITEM_B: 50})

	def test_consumption_accumulates(self):
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		self.pass_for(po, {ITEM: 60})
		self.pass_for(po, {ITEM: 30})
		self.assertEqual(self.pending(po), {ITEM: 10})

	def test_the_same_item_on_two_lines_is_tracked_separately(self):
		"""Keyed on the source ROW, not the item code.

		Keyed by item, consuming one line would wrongly appear to consume the
		other, and over-receipt on one could hide under-receipt on the other.
		"""
		po = make_purchase_order(self.masters, [(ITEM, 40), (ITEM, 60)])
		rows = [r.name for r in po.items]

		config = frappe.get_cached_doc("Gate Pass Source", self.flow)
		before = ledger.pending_qty("Purchase Order", po.name, config)
		self.assertEqual({r: before[r]["pending"] for r in rows}, {rows[0]: 40, rows[1]: 60})

		# Take the whole of the first line only.
		gp = gate_pass_from_source(self.flow, po.name)
		keep = [r for r in gp.items if r.source_row == rows[0]]
		keep[0].qty = keep[0].accepted_qty = 40
		gp.set("items", keep)
		gp.vehicle_number, gp.driver_name = "GP-TEST-0003", "Test Driver"
		gp.flags.ignore_permissions = True
		gp.insert(ignore_permissions=True)
		gp.submit()

		after = ledger.pending_qty("Purchase Order", po.name, config)
		self.assertEqual(
			{r: after[r]["pending"] for r in rows},
			{rows[0]: 0, rows[1]: 60},
			"consuming one line must not touch the other",
		)

	def test_a_draft_pass_consumes_nothing(self):
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		self.pass_for(po, {ITEM: 60}, submit=False)
		self.assertEqual(self.pending(po), {ITEM: 100}, "only submitted passes consume")

	def test_cancelling_releases_the_quantity(self):
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		gp = self.pass_for(po, {ITEM: 60})
		self.assertEqual(self.pending(po), {ITEM: 40})

		gp.cancel()
		self.assertEqual(self.pending(po), {ITEM: 100}, "a cancelled pass must give it back")

	def test_nothing_left_is_refused_with_an_explanation(self):
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		self.pass_for(po, {ITEM: 100})

		with self.assertRaises(frappe.ValidationError) as caught:
			gate_pass_from_source(self.flow, po.name)
		self.assertIn("already been gate passed", str(caught.exception))


class TestLockedRead(LedgerTest):
	def test_locked_and_display_reads_agree(self):
		"""`consumed_qty_for_update` is the one the rules trust. It must not
		disagree with the figure shown on the form."""
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		self.pass_for(po, {ITEM: 60})
		rows = [r.name for r in po.items]

		display = ledger.consumed_qty(rows)
		locked = ledger.consumed_qty_for_update(
			source_doctype="Purchase Order",
			source_documents=[po.name],
			source_rows=rows,
		)
		self.assertEqual(display, locked)
		self.assertEqual(flt(display[rows[0]]), 60)

	def test_excluding_a_pass_removes_only_that_one(self):
		"""How a pass avoids counting itself when it re-validates at submit."""
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		first = self.pass_for(po, {ITEM: 60})
		self.pass_for(po, {ITEM: 20})
		rows = [r.name for r in po.items]

		without_first = ledger.consumed_qty_for_update(
			source_doctype="Purchase Order",
			source_documents=[po.name],
			source_rows=rows,
			exclude_gate_pass=first.name,
		)
		self.assertEqual(flt(without_first.get(rows[0])), 20)

	def test_locking_an_unknown_document_does_not_explode(self):
		self.assertEqual(
			ledger.consumed_qty_for_update("Purchase Order", [], [], None), {}
		)


class TestOverQuantity(LedgerTest):
	def test_more_than_the_line_allows_is_refused_at_submit(self):
		"""The definitive check, which runs under the lock at submit."""
		from gate_pass_management.tests.utils import rule_action

		po = make_purchase_order(self.masters, [(ITEM, 100)])
		self.pass_for(po, {ITEM: 90})

		gp = gate_pass_from_source(self.flow, po.name)
		row = gp.items[0]
		row.qty = row.accepted_qty = 50  # 90 + 50 against a line of 100
		gp.vehicle_number, gp.driver_name = "GP-TEST-0004", "Test Driver"
		gp.flags.ignore_permissions = True

		with rule_action("QTY-LEDGER", "Block", threshold=0), rule_action(
			"QTY-ROW-PENDING", "Ignore"
		):
			gp.insert(ignore_permissions=True)
			with self.assertRaises(frappe.ValidationError) as caught:
				gp.submit()

		# The message is what the operator reads, so it is asserted on rather
		# than the rule code — codes are for Settings, not for the gate.
		message = str(caught.exception)
		self.assertIn("exceeds the ordered qty", message)
		self.assertIn("140", message, "should state the total being attempted")
		self.assertIn("90", message, "should state what other passes already took")

		# Read the database, not the in-memory object: submit() sets docstatus
		# before before_submit runs, so the stale object still says 1 while the
		# transaction that would have persisted it was rolled back.
		self.assertEqual(
			frappe.db.get_value("Gate Pass", gp.name, "docstatus"),
			0,
			"the pass must not be left submitted",
		)

	def test_within_tolerance_is_allowed(self):
		from gate_pass_management.tests.utils import rule_action

		po = make_purchase_order(self.masters, [(ITEM, 100)])
		gp = gate_pass_from_source(self.flow, po.name)
		row = gp.items[0]
		row.qty = row.accepted_qty = 105  # 5% over
		gp.vehicle_number, gp.driver_name = "GP-TEST-0005", "Test Driver"
		gp.flags.ignore_permissions = True

		with rule_action("QTY-LEDGER", "Block", threshold=10), rule_action(
			"QTY-ROW-PENDING", "Ignore"
		):
			gp.insert(ignore_permissions=True)
			gp.submit()

		self.assertEqual(gp.docstatus, 1)
