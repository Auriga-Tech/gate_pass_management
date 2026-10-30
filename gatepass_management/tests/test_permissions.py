"""Who may pull from a source document.

A gate operator has to take items off a Purchase Order without holding a Buying
role, because that role would also let them change prices and approve orders.
The pull endpoints therefore accept Gate Pass create permission in place of read
permission on the source doctype.

What must stay true, and is what these tests are really for:

  * the relaxation is reachable from the UI — the picker lists documents too,
    not just the endpoint behind it
  * User Permissions still apply, since once the role requirement is relaxed
    they are the only restriction a site has left
  * it is a relaxation for gate passes, not for everyone: a user who cannot
    create a Gate Pass gains nothing

The restriction here is written on Supplier rather than Company only because a
second Company drags in a chart of accounts. The mechanism is per link field, so
a Company or Gate Pass Location restriction behaves identically.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from gatepass_management.api import gate_pass as api
from gatepass_management.tests.utils import (
	ITEM,
	PREFIX,
	SUPPLIER,
	as_user,
	ensure_masters,
	ensure_user,
	make_purchase_order,
	source_name_for,
	user_permission,
)

OTHER_SUPPLIER = f"{PREFIX} Other Supplier"


class SourceAccessTest(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.masters = ensure_masters()
		cls.flow = source_name_for("Purchase Order", "In")
		cls.guard = ensure_user("gp-guard", ["Gate Pass Operator"])
		cls.auditor = ensure_user("gp-auditor", ["Gate Pass Auditor"])

		if not frappe.db.exists("Supplier", OTHER_SUPPLIER):
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": OTHER_SUPPLIER,
					"supplier_group": frappe.db.get_value("Supplier Group", {}, "name"),
				}
			).insert(ignore_permissions=True)

	def setUp(self):
		self.po = make_purchase_order(self.masters, [(ITEM, 100)])

	def query(self, **overrides):
		args = {
			"doctype": "Purchase Order",
			"txt": "",
			"searchfield": "name",
			"start": 0,
			"page_len": 20,
			"filters": {"gate_pass_source": self.flow},
		}
		args.update(overrides)
		return api.source_query(**args)

	def names(self, **overrides):
		return [r["name"] for r in self.query(**overrides)]


class TestTheGuardHasNoSourceRole(SourceAccessTest):
	def test_the_premise(self):
		"""If this ever fails the rest of the file is testing nothing."""
		with as_user(self.guard):
			self.assertFalse(
				frappe.has_permission("Purchase Order", "read"),
				"a gate operator must not hold Buying read — that is the whole problem",
			)
			self.assertTrue(frappe.has_permission("Gate Pass", "create"))


class TestTheGuardCanPull(SourceAccessTest):
	def test_the_picker_lists_the_order(self):
		"""The ordinary list query raises PermissionError here.

		Without a query of our own the dialog came back empty and the relaxation
		below could not be reached from the UI at all.
		"""
		with as_user(self.guard):
			with self.assertRaises(frappe.PermissionError):
				frappe.get_list("Purchase Order", fields=["name"], limit=1)
			self.assertIn(self.po.name, self.names())

	def test_pending_quantity(self):
		with as_user(self.guard):
			pending = api.get_pending("Purchase Order", self.po.name, self.flow)
		self.assertEqual([info["pending"] for info in pending.values()], [100])

	def test_building_the_gate_pass(self):
		with as_user(self.guard):
			gp = api.build_gate_pass(self.flow, self.po.name)
		self.assertEqual(gp.source_document, self.po.name)
		self.assertEqual([r.item_code for r in gp.items], [ITEM])


class TestUserPermissionsStillApply(SourceAccessTest):
	"""The scoped part. A guard restricted to one party, company or location
	must not be able to pull anything else, or the relaxation is an open door."""

	def test_the_picker_hides_a_restricted_order(self):
		with as_user(self.guard), user_permission(self.guard, "Supplier", OTHER_SUPPLIER):
			self.assertNotIn(self.po.name, self.names())

	def test_pending_quantity_is_refused(self):
		with as_user(self.guard), user_permission(self.guard, "Supplier", OTHER_SUPPLIER):
			with self.assertRaises(frappe.PermissionError):
				api.get_pending("Purchase Order", self.po.name, self.flow)

	def test_building_is_refused(self):
		with as_user(self.guard), user_permission(self.guard, "Supplier", OTHER_SUPPLIER):
			with self.assertRaises(frappe.PermissionError):
				api.build_gate_pass(self.flow, self.po.name)

	def test_a_permitted_order_is_still_reachable(self):
		"""The restriction must bite on the wrong order, not on every order."""
		with as_user(self.guard), user_permission(self.guard, "Supplier", SUPPLIER):
			self.assertIn(self.po.name, self.names())
			api.get_pending("Purchase Order", self.po.name, self.flow)


class TestTheDialogReachesIt(SourceAccessTest):
	def test_through_search_widget_as_the_dialog_calls_it(self):
		"""The real client contract, not a direct call to our function.

		MultiSelectDialog sends its filters as [doctype, field, op, value]
		tuples and lets `search_widget` turn them back into a dict, and it
		passes kwargs our signature does not declare. Calling `source_query`
		directly tests none of that.
		"""
		from frappe.desk.search import search_widget

		with as_user(self.guard):
			rows = search_widget(
				doctype="Purchase Order",
				txt="",
				query="gatepass_management.api.gate_pass.source_query",
				searchfield="name",
				start=0,
				page_length=25,
				filters=[
					["Purchase Order", "gate_pass_source", "=", self.flow],
					["Purchase Order", "supplier", "=", SUPPLIER],
				],
				query_filters_as_dict=True,
				as_dict=1,
			)

		# Dicts carrying `name`, which is what the dialog renders and checks.
		self.assertTrue(rows)
		self.assertIn(self.po.name, [r["name"] for r in rows])
		self.assertEqual(rows[0]["supplier"], SUPPLIER)

	def test_typing_in_the_search_box_narrows_the_list(self):
		with as_user(self.guard):
			self.assertIn(self.po.name, self.names(txt=self.po.name[-4:]))
			self.assertEqual(self.names(txt="ZZ-no-such-document"), [])

	def test_the_party_setter_narrows_the_list(self):
		other = make_purchase_order(self.masters, [(ITEM, 1)])
		frappe.db.set_value("Purchase Order", other.name, "supplier", OTHER_SUPPLIER)

		with as_user(self.guard):
			names = self.names(
				filters={"gate_pass_source": self.flow, "supplier": OTHER_SUPPLIER}
			)
		self.assertIn(other.name, names)
		self.assertNotIn(self.po.name, names)


class TestItIsNotAGeneralRelaxation(SourceAccessTest):
	def test_without_gate_pass_create_nothing_is_granted(self):
		"""An auditor may read gate passes and nothing else. Read access to
		every Purchase Order on the site is not part of that."""
		with as_user(self.auditor):
			self.assertFalse(frappe.has_permission("Gate Pass", "create"))
			with self.assertRaises(frappe.PermissionError):
				api.get_pending("Purchase Order", self.po.name, self.flow)
			with self.assertRaises(frappe.PermissionError):
				self.query()

	def test_the_query_is_tied_to_one_flow(self):
		with as_user(self.guard):
			# No flow at all.
			with self.assertRaises(frappe.ValidationError):
				self.query(filters={})
			# A flow that does not draw from the doctype being listed.
			with self.assertRaises(frappe.PermissionError):
				self.query(doctype="Delivery Note")

	def test_only_submitted_documents_are_offered(self):
		"""`build_gate_pass` refuses a draft, so offering one is a dead end."""
		draft = make_purchase_order(self.masters, [(ITEM, 10)], submit=False)
		with as_user(self.guard):
			names = self.names()
		self.assertIn(self.po.name, names)
		self.assertNotIn(draft.name, names)

	def test_client_filters_cannot_widen_the_flow(self):
		"""A flow's configured filters are applied server side, so a crafted
		call cannot ask for documents the flow excludes."""
		with as_user(self.guard):
			names = self.names(filters={"gate_pass_source": self.flow, "docstatus": 0})
		self.assertNotIn(
			make_purchase_order(self.masters, [(ITEM, 5)], submit=False).name, names
		)
