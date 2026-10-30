"""The flows end to end.

A gate pass is only worth anything if what the gate counted reaches the stock
ledger unchanged. These walk the whole path — order, pass, receipt — and assert
on the receipt, because that is the document the business acts on.

The discrepancy mapping here makes one deliberate choice: damaged goods are physically present and become rejected qty, but
short goods never arrived and are simply not received. Booking them would create
stock that does not exist and close the order line.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, flt, today

from gate_pass_management.targets.create import create_target
from gate_pass_management.tests.utils import (
	ITEM,
	ITEM_B,
	SUPPLIER,
	SUPPLIER_B,
	allowed_party_types,
	ensure_cost_center,
	ensure_masters,
	gate_pass_from_source,
	make_gate_pass,
	make_party_address,
	make_party_contact,
	make_purchase_order,
	setting,
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

	def test_goods_rejected_at_the_gate_become_rejected_qty(self):
		"""Rejected at Gate is booked like damage: it
		went through the gate, so the receipt holds it in the rejected warehouse
		and accounts for the whole consignment."""
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		gp = self.gate_pass_for(
			po, qty=100, accepted_qty=90, damaged_qty=4, rejected_qty=6,
			rejected_warehouse=self.masters["rejected"],
		)

		pr = frappe.get_doc("Purchase Receipt", create_target(gp.name, "Purchase Receipt")["created"][0])
		row = pr.items[0]
		self.assertEqual(flt(row.qty), 90)
		self.assertEqual(flt(row.rejected_qty), 10, "damaged 4 + rejected at gate 6")
		self.assertEqual(flt(row.received_qty), 100)
		self.assertEqual(row.rejected_warehouse, self.masters["rejected"])

	def test_shortage_is_not_received_by_default(self):
		"""The default, and a deliberate choice: shortage is not booked as received.

		Short goods did not arrive. Booking them as rejected qty would write a
		Stock Ledger Entry for stock that does not exist and close the order
		line, so the shortage would never be chased. A site that wants the
		other behaviour says so in Settings; see TestShortageHandling.
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


class TestCostCenter(FlowTest):
	def pass_with(self, po, cost_center=None):
		gp = gate_pass_from_source(self.flow, po.name)
		gp.cost_center = cost_center
		gp.vehicle_number, gp.driver_name = "GP-FLOW-0002", "Test Driver"
		gp.flags.ignore_permissions = True
		gp.insert(ignore_permissions=True)
		gp.submit()
		return gp

	def receipt(self, gp):
		return frappe.get_doc("Purchase Receipt", create_target(gp.name, "Purchase Receipt")["created"][0])

	def test_the_chosen_cost_center_reaches_the_receipt_rows(self):
		"""Purchase Receipt holds its cost center on the rows alone."""
		chosen = ensure_cost_center(self.masters)
		po = make_purchase_order(self.masters, [(ITEM, 10)])
		self.assertNotEqual(po.items[0].cost_center, chosen, "premise: the order carries another")

		pr = self.receipt(self.pass_with(po, chosen))
		self.assertEqual([row.cost_center for row in pr.items], [chosen])

	def test_left_blank_the_orders_own_cost_center_is_kept(self):
		"""No choice on the gate pass means ERPNext's mapper stands."""
		po = make_purchase_order(self.masters, [(ITEM, 10)])
		pr = self.receipt(self.pass_with(po))
		self.assertEqual(pr.items[0].cost_center, po.items[0].cost_center)


class TestShortageHandling(FlowTest):
	"""Gate Pass Settings > Shortage on the Receipt.

	Two sites disagreed about whether a counted shortage belongs on the receipt,
	and neither is wrong: it is an accounting decision. So it is a setting.
	"""

	def receipt_row(self, **row_values):
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		gp = self.gate_pass_for(po, qty=100, accepted_qty=94, rejected_warehouse=self.masters["rejected"], **row_values)
		pr = frappe.get_doc("Purchase Receipt", create_target(gp.name, "Purchase Receipt")["created"][0])
		return pr.items[0]

	def test_the_default_is_not_received(self):
		self.assertEqual(
			frappe.db.get_single_value("Gate Pass Settings", "shortage_handling"), "Not Received"
		)

	def test_book_as_rejected_carries_the_shortage_over(self):
		with setting(shortage_handling="Book as Rejected"):
			row = self.receipt_row(shortage_qty=6)

		self.assertEqual(flt(row.qty), 94, "accepted is unchanged")
		self.assertEqual(flt(row.rejected_qty), 6, "the shortage is booked as rejected")
		self.assertEqual(flt(row.received_qty), 100, "every unit on the order is accounted for")
		self.assertEqual(row.rejected_warehouse, self.masters["rejected"])

	def test_damage_and_shortage_add_together(self):
		with setting(shortage_handling="Book as Rejected"):
			row = self.receipt_row(damaged_qty=4, shortage_qty=2)

		self.assertEqual(flt(row.rejected_qty), 6)
		self.assertEqual(flt(row.received_qty), 100)

	def test_not_received_leaves_the_shortage_out(self):
		with setting(shortage_handling="Not Received"):
			row = self.receipt_row(shortage_qty=6)

		self.assertEqual(flt(row.rejected_qty), 0)
		self.assertEqual(flt(row.received_qty), 94)

	def test_damage_is_booked_whichever_way_it_is_set(self):
		for choice in ("Not Received", "Book as Rejected"):
			with self.subTest(choice=choice), setting(shortage_handling=choice):
				row = self.receipt_row(damaged_qty=6)
				self.assertEqual(flt(row.rejected_qty), 6)

	def test_a_booked_shortage_needs_a_rejected_warehouse(self):
		"""Same refusal as damage, naming the gate pass row rather than failing
		inside ERPNext where nothing points at it."""
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		with setting(shortage_handling="Book as Rejected", default_rejected_warehouse=""):
			gp = self.gate_pass_for(po, qty=100, accepted_qty=94, shortage_qty=6)
			with self.assertRaises(frappe.ValidationError) as caught:
				create_target(gp.name, "Purchase Receipt", raise_on_error=True)
		self.assertIn("Rejected Warehouse", str(caught.exception))


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


class TestMultiSourcePass(FlowTest):
	"""One truck, one supplier, several purchase orders, one gate pass."""

	def _pass_for(self, *pos, **row_values):
		gp = gate_pass_from_source(self.flow, [p.name for p in pos])
		for row in gp.items:
			for field, value in row_values.items():
				setattr(row, field, value)
		gp.vehicle_number = "GP-FLOW-0001"
		gp.driver_name = "Test Driver"
		gp.insert(ignore_permissions=True)
		return gp

	def test_two_orders_from_one_supplier_share_a_pass(self):
		po1 = make_purchase_order(self.masters, [(ITEM, 100)])
		po2 = make_purchase_order(self.masters, [(ITEM_B, 40)])

		gp = self._pass_for(po1, po2)

		self.assertEqual(len(gp.items), 2)
		self.assertEqual({r.source_document for r in gp.items}, {po1.name, po2.name})
		self.assertEqual(gp.is_multi_source, 1, "a pass over two documents says so")
		self.assertEqual(gp.party, SUPPLIER)

	def test_each_order_gets_its_own_receipt(self):
		po1 = make_purchase_order(self.masters, [(ITEM, 100)])
		po2 = make_purchase_order(self.masters, [(ITEM_B, 40)])
		gp = self._pass_for(po1, po2)
		gp.submit()

		result = create_target(gp.name, "Purchase Receipt")

		self.assertEqual(result["failed"], [])
		self.assertEqual(len(result["created"]), 2, "one receipt per purchase order")
		pos_received = set()
		for name in result["created"]:
			pr = frappe.get_doc("Purchase Receipt", name)
			self.assertEqual(len(pr.items), 1)
			pos_received.add(pr.items[0].purchase_order)
		self.assertEqual(pos_received, {po1.name, po2.name})

	def test_a_second_supplier_is_refused(self):
		po1 = make_purchase_order(self.masters, [(ITEM, 100)])
		other = make_purchase_order(self.masters, [(ITEM_B, 40)], supplier=SUPPLIER_B)

		with self.assertRaises(frappe.ValidationError) as ctx:
			gate_pass_from_source(self.flow, [po1.name, other.name])
		self.assertIn("One Gate Pass covers one party", str(ctx.exception))

	def test_a_second_supplier_is_refused_on_a_draft_that_already_has_rows(self):
		from gate_pass_management.api.gate_pass import build_gate_pass

		po1 = make_purchase_order(self.masters, [(ITEM, 100)])
		other = make_purchase_order(self.masters, [(ITEM_B, 40)], supplier=SUPPLIER_B)
		draft = gate_pass_from_source(self.flow, po1.name)

		with self.assertRaises(frappe.ValidationError):
			build_gate_pass(self.flow, other.name, frappe.as_json(draft.as_dict()))

	def test_the_same_order_is_not_added_twice(self):
		from gate_pass_management.api.gate_pass import build_gate_pass

		po1 = make_purchase_order(self.masters, [(ITEM, 100)])
		draft = gate_pass_from_source(self.flow, po1.name)

		with self.assertRaises(frappe.ValidationError) as ctx:
			build_gate_pass(self.flow, po1.name, frappe.as_json(draft.as_dict()))
		self.assertIn("already on this Gate Pass", str(ctx.exception))

		# Listing it twice in one pull must not double the quantity either.
		both = gate_pass_from_source(self.flow, [po1.name, po1.name])
		self.assertEqual(len(both.items), 1)
		self.assertEqual(flt(both.items[0].qty), 100)

	def test_a_later_order_can_be_added_to_an_open_draft(self):
		from gate_pass_management.api.gate_pass import build_gate_pass

		po1 = make_purchase_order(self.masters, [(ITEM, 100)])
		po2 = make_purchase_order(self.masters, [(ITEM_B, 40)])
		draft = gate_pass_from_source(self.flow, po1.name)

		merged = build_gate_pass(self.flow, po2.name, frappe.as_json(draft.as_dict()))

		self.assertEqual({r.source_document for r in merged.items}, {po1.name, po2.name})


class TestPickerHidesFullyPassedDocuments(FlowTest):
	"""Gate Pass Settings > Hide Fully Gate-Passed Documents in the Picker."""

	def listed(self, **overrides):
		from gate_pass_management.api.gate_pass import source_query

		args = {
			"doctype": "Purchase Order", "txt": "", "searchfield": "name",
			"start": 0, "page_len": 50, "filters": {"gate_pass_source": self.flow},
		}
		args.update(overrides)
		return [r["name"] for r in source_query(**args)]

	def passed_order(self):
		"""A purchase order whose every line is on a submitted gate pass."""
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		self.gate_pass_for(po, qty=100, accepted_qty=100)
		return po

	def test_a_fully_passed_order_is_hidden_and_an_open_one_is_not(self):
		done = self.passed_order()
		open_po = make_purchase_order(self.masters, [(ITEM, 100)])

		with setting(hide_fully_passed_documents=1):
			names = self.listed()

		self.assertNotIn(done.name, names)
		self.assertIn(open_po.name, names)

	def test_switching_the_setting_off_lists_everything_again(self):
		done = self.passed_order()

		with setting(hide_fully_passed_documents=0):
			self.assertIn(done.name, self.listed())

	def test_an_order_with_some_quantity_left_stays_listed(self):
		po = make_purchase_order(self.masters, [(ITEM, 100)])
		self.gate_pass_for(po, qty=40, accepted_qty=40)

		with setting(hide_fully_passed_documents=1):
			self.assertIn(po.name, self.listed(), "60 of 100 are still to come")

	def test_paging_counts_what_is_shown_not_what_was_skipped(self):
		"""Page two must start after the last listed order, not after the last
		scanned one, or the orders hidden in between would eat part of the page."""
		first = make_purchase_order(self.masters, [(ITEM, 10)])
		self.passed_order()
		self.passed_order()
		last = make_purchase_order(self.masters, [(ITEM, 10)])

		with setting(hide_fully_passed_documents=1):
			everything = self.listed()
			page_one = self.listed(page_len=1)
			page_two = self.listed(page_len=1, start=1)

		open_names = [n for n in everything if n in (first.name, last.name)]
		self.assertEqual(len(open_names), 2)
		self.assertEqual(page_one + page_two, open_names[:2])

	def test_the_setting_exists_and_defaults_on(self):
		self.assertEqual(
			frappe.get_meta("Gate Pass Settings").get_field("hide_fully_passed_documents").default, "1"
		)
		self.assertEqual(
			frappe.db.get_single_value("Gate Pass Settings", "hide_fully_passed_documents"), 1
		)


class TestSeriesFollowsDirection(FlowTest):
	"""With a series per direction, an inward pass is named GP-IN and an
	outward one GP-OUT, whatever the form happened to be showing."""

	IN, OUT = "GP-IN-.YYYY.-", "GP-OUT-.YYYY.-"

	def _settings(self, **values):
		"""Saved through the doctype, so the Series options are rebuilt as they
		are when an administrator changes these fields on the form."""
		settings = frappe.get_single("Gate Pass Settings")
		self._before = getattr(self, "_before", {})
		for k in values:
			self._before.setdefault(k, settings.get(k))  # the first value is the one to restore
		settings.update(values)
		settings.save(ignore_permissions=True)
		frappe.clear_cache()

	def tearDown(self):
		before = getattr(self, "_before", None)
		if before:
			settings = frappe.get_single("Gate Pass Settings")
			settings.update(before)
			settings.save(ignore_permissions=True)
			frappe.clear_cache()
		super().tearDown()

	def _separate(self):
		self._settings(
			separate_series_by_direction=1, naming_series_in=self.IN, naming_series_out=self.OUT
		)

	def test_an_inward_pass_takes_the_inward_series(self):
		self._separate()
		gp = make_gate_pass(self.masters, direction="In")
		self.assertTrue(gp.name.startswith("GP-IN-"), gp.name)

	def test_an_outward_pass_takes_the_outward_series(self):
		self._separate()
		gp = make_gate_pass(self.masters, direction="Out")
		self.assertTrue(gp.name.startswith("GP-OUT-"), gp.name)

	def test_a_series_chosen_against_the_direction_is_corrected(self):
		self._separate()
		gp = make_gate_pass(self.masters, direction="In", naming_series=self.OUT)
		self.assertTrue(gp.name.startswith("GP-IN-"), "the direction wins: " + gp.name)

	def test_a_pass_from_a_flow_is_named_by_the_flows_direction(self):
		"""Naming runs before the direction is derived, so it must read the flow."""
		self._separate()
		po = make_purchase_order(self.masters, [(ITEM, 10)])
		gp = gate_pass_from_source(self.flow, po.name)
		gp.direction = "Out"
		gp.vehicle_number, gp.driver_name = "GP-FLOW-0001", "Test Driver"
		gp.insert(ignore_permissions=True)
		self.assertTrue(gp.name.startswith("GP-IN-"), gp.name)

	def test_with_one_series_for_both_the_choice_stands(self):
		self._settings(
			separate_series_by_direction=0, naming_series="GP-.YYYY.-\nGP-IN-.YYYY.-"
		)
		gp = make_gate_pass(self.masters, direction="Out", naming_series="GP-IN-.YYYY.-")
		self.assertTrue(gp.name.startswith("GP-IN-"), gp.name)

	def test_the_form_asks_for_the_series_by_direction(self):
		from gate_pass_management.api.gate_pass import get_series_for_direction

		self._separate()
		self.assertEqual(get_series_for_direction("In"), self.IN)
		self.assertEqual(get_series_for_direction("Out"), self.OUT)
		self.assertIsNone(get_series_for_direction("Sideways"))

		self._settings(separate_series_by_direction=0)
		self.assertIsNone(get_series_for_direction("In"), "one series: nothing to impose")


class TestAllowedPartyTypes(FlowTest):
	"""Gate Pass Settings > Allowed Party Types."""

	def test_a_party_type_outside_the_list_is_refused(self):
		with allowed_party_types("Supplier"):
			with self.assertRaises(frappe.ValidationError) as ctx:
				make_gate_pass(self.masters, party_type="Customer", party=None)
		self.assertIn("not an allowed Party Type", str(ctx.exception))

	def test_a_listed_party_type_is_accepted(self):
		with allowed_party_types("Supplier", "Customer"):
			gp = make_gate_pass(self.masters, party_type="Supplier", party=SUPPLIER)
		self.assertEqual(gp.party_type, "Supplier")

	def test_a_flow_whose_party_is_not_allowed_cannot_make_a_pass(self):
		"""A purchase order pulls in a Supplier; with only Customer allowed the
		pass is refused rather than saved with a party type the site banned."""
		po = make_purchase_order(self.masters, [(ITEM, 10)])
		with allowed_party_types("Customer"):
			gp = gate_pass_from_source(self.flow, po.name)
			gp.vehicle_number, gp.driver_name = "GP-FLOW-0001", "Test Driver"
			with self.assertRaises(frappe.ValidationError):
				gp.insert(ignore_permissions=True)

	def test_an_empty_list_restricts_nothing(self):
		with allowed_party_types():
			gp = make_gate_pass(self.masters, party_type="Supplier", party=SUPPLIER)
		self.assertTrue(gp.name)

	def test_the_dropdown_offers_only_the_allowed_types(self):
		from gate_pass_management.api.gate_pass import party_type_query

		def offered(txt=""):
			return [r[0] for r in party_type_query("DocType", txt, "name", 0, 20, {})]

		with allowed_party_types("Supplier", "Customer"):
			self.assertEqual(offered(), ["Supplier", "Customer"])
			self.assertEqual(offered("cust"), ["Customer"])

		with allowed_party_types():
			self.assertIn("Employee", offered("employee"), "nothing listed, nothing hidden")

	def test_a_default_the_list_excludes_is_refused_on_save(self):
		settings = frappe.get_single("Gate Pass Settings")
		with allowed_party_types("Supplier", "Customer"):
			settings = frappe.get_single("Gate Pass Settings")
			settings.default_party_type = "Company"
			with self.assertRaises(frappe.ValidationError) as ctx:
				settings.save(ignore_permissions=True)
		self.assertIn("not in Allowed Party Types", str(ctx.exception))


class TestPurposeFitsTheDirection(FlowTest):
	"""A Gate Pass Purpose carries a direction; the pass must agree with it."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from gate_pass_management.setup import fixtures

		fixtures.seed_purposes()

	def test_a_purpose_for_the_other_direction_is_refused(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			make_gate_pass(self.masters, direction="In", purpose="Sales Dispatch")
		self.assertIn("is for Out passes", str(ctx.exception))

	def test_a_matching_purpose_is_accepted(self):
		gp = make_gate_pass(self.masters, direction="In", purpose="Purchase Delivery")
		self.assertEqual(gp.purpose, "Purchase Delivery")

	def test_a_purpose_for_both_directions_fits_either(self):
		for direction in ("In", "Out"):
			gp = make_gate_pass(self.masters, direction=direction, purpose="Stock Transfer")
			self.assertEqual(gp.purpose, "Stock Transfer")

	def _retire(self, purpose):
		frappe.db.set_value("Gate Pass Purpose", purpose, "is_active", 0)
		self.addCleanup(frappe.db.set_value, "Gate Pass Purpose", purpose, "is_active", 1)

	def test_a_retired_purpose_cannot_be_chosen(self):
		self._retire("Scrap Disposal")
		with self.assertRaises(frappe.ValidationError) as ctx:
			make_gate_pass(self.masters, direction="Out", purpose="Scrap Disposal")
		self.assertIn("no longer active", str(ctx.exception))

	def test_retiring_a_purpose_does_not_break_a_pass_already_using_it(self):
		gp = make_gate_pass(self.masters, direction="Out", purpose="Scrap Disposal")
		self._retire("Scrap Disposal")

		gp.reload()
		gp.driver_name = "Someone Else"
		gp.save(ignore_permissions=True)  # must not raise: the purpose itself is unchanged
		self.assertEqual(gp.purpose, "Scrap Disposal")


class TestPartyAddressAndContact(FlowTest):
	"""The address and contact on a pass must belong to its party."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.own_address = make_party_address(SUPPLIER, "GPTEST Own Address").name
		cls.other_address = make_party_address(SUPPLIER_B, "GPTEST Other Address").name
		cls.own_contact = make_party_contact(SUPPLIER, "GPTEST Own", "9876500001").name
		cls.other_contact = make_party_contact(SUPPLIER_B, "GPTEST Other", "9876500002").name

	def test_another_partys_address_is_refused(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			make_gate_pass(self.masters, address=self.other_address)
		self.assertIn("is not linked to", str(ctx.exception))

	def test_another_partys_contact_is_refused(self):
		with self.assertRaises(frappe.ValidationError) as ctx:
			make_gate_pass(self.masters, contact_person=self.other_contact)
		self.assertIn("is not linked to", str(ctx.exception))

	def test_the_partys_own_address_and_contact_are_accepted(self):
		gp = make_gate_pass(self.masters, address=self.own_address, contact_person=self.own_contact)
		self.assertEqual(gp.address, self.own_address)
		self.assertEqual(gp.contact_person, self.own_contact)

	def test_the_contacts_mobile_is_filled_in_when_left_blank(self):
		gp = make_gate_pass(self.masters, contact_person=self.own_contact)
		self.assertEqual(gp.contact_mobile, "9876500001")

	def test_a_typed_mobile_is_not_overwritten(self):
		gp = make_gate_pass(self.masters, contact_person=self.own_contact, contact_mobile="1111111111")
		self.assertEqual(gp.contact_mobile, "1111111111")

	def test_the_lists_offer_only_this_partys_own(self):
		from gate_pass_management.api.gate_pass import party_address_query, party_contact_query

		mine = {"link_doctype": "Supplier", "link_name": SUPPLIER}
		addresses = [r[0] for r in party_address_query("Address", "", "name", 0, 20, mine)]
		contacts = [r[0] for r in party_contact_query("Contact", "", "name", 0, 20, mine)]

		self.assertIn(self.own_address, addresses)
		self.assertNotIn(self.other_address, addresses)
		self.assertIn(self.own_contact, contacts)
		self.assertNotIn(self.other_contact, contacts)

	def test_the_lists_are_empty_until_a_party_is_chosen(self):
		from gate_pass_management.api.gate_pass import party_address_query, party_contact_query

		self.assertEqual(party_address_query("Address", "", "name", 0, 20, {}), [])
		self.assertEqual(party_contact_query("Contact", "", "name", 0, 20, {"link_doctype": "Supplier"}), [])

	def test_a_pass_saved_before_the_rule_keeps_its_address(self):
		"""Judged only when something relevant changes; an unrelated save is not."""
		gp = make_gate_pass(self.masters)
		frappe.db.set_value("Gate Pass", gp.name, "address", self.other_address)

		gp.reload()
		gp.driver_name = "Another Driver"
		gp.save(ignore_permissions=True)  # must not raise
		self.assertEqual(gp.address, self.other_address)
