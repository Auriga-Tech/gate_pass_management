"""The Gate Pass connection on ERPNext documents.

A document can relate to a gate pass two ways round. As the SOURCE it is what
the pass was raised from, and Frappe counts that off a field on Gate Pass. As the
TARGET it is what the pass produced, and the link is a field on the document
itself. The badge used to count only the first, so a Purchase Receipt created
from a gate pass showed no gate pass at all.
"""

from frappe.desk.notifications import get_open_count
from frappe.tests.utils import FrappeTestCase

from gatepass_management.targets.create import create_target
from gatepass_management.tests.utils import (
	ITEM,
	ensure_masters,
	gate_pass_from_source,
	make_purchase_order,
	source_name_for,
)


class TestConnectionBadge(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.masters = ensure_masters()
		cls.flow = source_name_for("Purchase Order", "In")

	def setUp(self):
		self.po = make_purchase_order(self.masters, [(ITEM, 100)])
		gp = gate_pass_from_source(self.flow, self.po.name)
		gp.vehicle_number, gp.driver_name = "GP-DASH-0001", "Test Driver"
		gp.flags.ignore_permissions = True
		gp.insert(ignore_permissions=True)
		gp.submit()
		self.gp = gp

	def count(self, doctype, name) -> dict:
		out = get_open_count(doctype, name, ["Gate Pass"])["count"]
		return {
			"internal": {d["doctype"]: d for d in out["internal_links_found"]},
			"external": {d["doctype"]: d for d in out["external_links_found"]},
		}

	def test_the_source_counts_the_pass_raised_from_it(self):
		found = self.count("Purchase Order", self.po.name)
		self.assertEqual(found["external"]["Gate Pass"]["count"], 1)

	def test_the_target_counts_the_pass_that_produced_it(self):
		"""The gap: this used to read zero."""
		pr = create_target(self.gp.name, "Purchase Receipt")["created"][0]

		found = self.count("Purchase Receipt", pr)
		self.assertIn("Gate Pass", found["internal"], "receipt shows no connection to its pass")
		self.assertEqual(found["internal"]["Gate Pass"]["names"], [self.gp.name])
		self.assertEqual(found["internal"]["Gate Pass"]["count"], 1)

	def test_a_document_with_no_pass_reports_none(self):
		other = make_purchase_order(self.masters, [(ITEM, 5)])
		found = self.count("Purchase Order", other.name)
		self.assertEqual(found["external"]["Gate Pass"]["count"], 0)
