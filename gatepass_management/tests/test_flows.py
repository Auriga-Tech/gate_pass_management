"""The flows end to end.

A gate pass is only worth anything if what the gate counted reaches the stock
ledger unchanged. These walk the whole path — order, pass, receipt — and assert
on the receipt, because that is the document the business acts on.

The discrepancy mapping here is the one deliberate disagreement with the
SJDM branch: damaged goods are physically present and become rejected qty, but
short goods never arrived and are simply not received. Booking them would create
stock that does not exist and close the order line.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from gatepass_management.targets.create import create_target
from gatepass_management.tests.utils import (
	ITEM,
	ITEM_B,
	SUPPLIER,
	ensure_masters,
	gate_pass_from_source,
	make_gate_pass,
	make_purchase_order,
	source_name_for,
)


class FlowTest(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.masters = ensure_masters()
		cls.flow = source_name_for("Purchase Order", "In")

	def gate_pass_for(self, po, **row_values):
		gp = gate_pass_from_source(self.flow, po.name)
		for row in gp.items:
			for field, value in row_values.items():
				setattr(row, field, value)
		gp.vehicle_number = "GP-FLOW-0001"
		gp.driver_name = "Test Driver"
		gp.flags.ignore_permissions = True
		gp.insert(ignore_permissions=True)
		gp.submit()
		return gp


class TestPurchaseFlow(FlowTest):
	def test_a_clean_receipt_carries_the_gate_count(self):
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		gp = self.gate_pass_for(po, qty=100, accepted_qty=100)

		result = create_target(gp.name, "Purchase Receipt")
		self.assertEqual(result["failed"], [], "nothing should have failed")
		self.assertEqual(len(result["created"]), 1)

		pr = frappe.get_doc("Purchase Receipt", result["created"][0])
		self.assertEqual(pr.gate_pass, gp.name, "the receipt must point back at the pass")
		self.assertEqual(flt(pr.items[0].qty), 100)

	def test_damaged_goods_become_rejected_qty(self):
		"""Damaged stock is present, so it is received into the rejected
		warehouse rather than quietly dropped."""
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		gp = self.gate_pass_for(
			po, qty=100, accepted_qty=94, damaged_qty=6,
			rejected_warehouse=self.masters["rejected"],
		)

		pr = frappe.get_doc("Purchase Receipt", create_target(gp.name, "Purchase Receipt")["created"][0])
		row = pr.items[0]
		self.assertEqual(flt(row.qty), 94, "accepted qty is what is received")
		self.assertEqual(flt(row.rejected_qty), 6)
		self.assertEqual(flt(row.received_qty), 100, "accepted + damaged both arrived")
		self.assertEqual(row.rejected_warehouse, self.masters["rejected"])

	def test_shortage_is_never_received(self):
		"""The deliberate disagreement with the SJDM branch.

		Short goods did not arrive. Booking them as rejected qty would write a
		Stock Ledger Entry for stock that does not exist and close the order
		line, so the shortage would never be chased.
		"""
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		gp = self.gate_pass_for(po, qty=100, accepted_qty=94, shortage_qty=6)

		pr = frappe.get_doc("Purchase Receipt", create_target(gp.name, "Purchase Receipt")["created"][0])
		row = pr.items[0]
		self.assertEqual(flt(row.qty), 94)
		self.assertEqual(flt(row.rejected_qty), 0, "shortage must not become rejected stock")
		self.assertEqual(flt(row.received_qty), 94, "only what arrived is received")

		po.reload()
		self.assertLess(
			flt(po.items[0].received_qty), 100, "the order line must stay open for the shortfall"
		)

	def test_creating_the_same_target_twice_is_refused(self):
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		gp = self.gate_pass_for(po, qty=100, accepted_qty=100)
		create_target(gp.name, "Purchase Receipt")

		with self.assertRaises(frappe.ValidationError) as caught:
			create_target(gp.name, "Purchase Receipt")
		self.assertIn("already been processed", str(caught.exception))

	def test_processing_marks_the_pass_complete(self):
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		gp = self.gate_pass_for(po, qty=100, accepted_qty=100)
		create_target(gp.name, "Purchase Receipt")

		gp.reload()
		self.assertEqual(flt(gp.per_processed), 100)
		self.assertEqual(gp.status, "Completed")

	def test_a_partly_damaged_pass_still_reaches_a_hundred_percent(self):
		"""Only accepted qty can ever be received, so it is the denominator.

		Measured against the paperwork this pass would stop at 94% and sit on
		the Pending worklist for ever.
		"""
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		gp = self.gate_pass_for(
			po, qty=100, accepted_qty=94, damaged_qty=6,
			rejected_warehouse=self.masters["rejected"],
		)
		create_target(gp.name, "Purchase Receipt")

		gp.reload()
		self.assertEqual(flt(gp.per_processed), 100)
		self.assertEqual(gp.status, "Completed")

	def test_cancelling_the_receipt_frees_the_pass_again(self):
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		gp = self.gate_pass_for(po, qty=100, accepted_qty=100)
		pr = frappe.get_doc("Purchase Receipt", create_target(gp.name, "Purchase Receipt")["created"][0])
		pr.submit()
		pr.cancel()

		gp.reload()
		self.assertLess(flt(gp.per_processed), 100, "a cancelled receipt releases the pass")


class TestCancellingAReceipt(FlowTest):
	def test_erpnexts_own_link_exclusions_survive(self):
		"""The tuple-versus-list bug.

		ERPNext sets `ignore_linked_doctypes` as a tuple of its own ledger
		doctypes during cancel. Replacing it instead of adding to it threw those
		away and cancelling failed on the receipt's own GL entries.
		"""
		po = make_purchase_order(self.masters, [(ITEM, 10)])
		gp = self.gate_pass_for(po, qty=10, accepted_qty=10)
		pr = frappe.get_doc("Purchase Receipt", create_target(gp.name, "Purchase Receipt")["created"][0])
		pr.submit()

		pr.cancel()  # must not raise
		self.assertEqual(pr.docstatus, 2)


class TestReturnableFlow(FlowTest):
	def outward(self, qty=10):
		return make_gate_pass(
			self.masters,
			direction="Out",
			gate_pass_type="Returnable Material",
			is_returnable=1,
			expected_return_date=add_days(today(), 7),
			rows=[{"item_name": "Test tooling", "uom": "Nos", "qty": qty}],
			submit=True,
		)

	def return_leg(self, origin, qty):
		leg = make_gate_pass(
			self.masters,
			direction="In",
			gate_pass_type="Returnable Material",
			source_doctype="Gate Pass",
			source_document=origin.name,
			rows=[
				{
					"item_name": "Test tooling",
					"uom": "Nos",
					"qty": qty,
					"source_doctype": "Gate Pass",
					"source_document": origin.name,
				}
			],
			submit=True,
		)
		origin.reload()
		return leg

	def test_a_due_date_is_filled_in_when_left_blank(self):
		"""Without one the overdue scheduler can never select the pass."""
		gp = make_gate_pass(
			self.masters, direction="Out", gate_pass_type="Returnable Material",
			is_returnable=1, rows=[{"item_name": "Tool", "uom": "Nos", "qty": 1}],
		)
		self.assertTrue(gp.expected_return_date, "a returnable pass needs a due date")

	def test_the_loop_closes(self):
		out = self.outward(10)
		self.assertEqual(out.return_status, "Pending")

		self.return_leg(out, 4)
		self.assertEqual(flt(out.returned_qty), 4)
		self.assertEqual(out.return_status, "Partially Returned")

		second = self.return_leg(out, 6)
		self.assertEqual(flt(out.returned_qty), 10)
		self.assertEqual(out.return_status, "Returned")
		self.assertTrue(out.actual_return_date)

		# And a cancelled leg gives the quantity back.
		second.cancel()
		out.reload()
		self.assertEqual(flt(out.returned_qty), 4)
		self.assertEqual(out.return_status, "Partially Returned")

	def test_each_return_is_recorded_in_the_audit_trail(self):
		out = self.outward(10)
		self.return_leg(out, 4)

		events = frappe.get_all(
			"Gate Pass Event Log",
			filters={"gate_pass": out.name, "event": "Return Recorded"},
			pluck="message",
		)
		self.assertTrue(events, "a return must leave a trace on the outward pass")
