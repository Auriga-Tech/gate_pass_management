"""What a compliance check writes back onto the gate pass.

The runner is jurisdiction neutral, so a provider says which Gate Pass field
should receive its document number (`populates`) and the runner copies it. The
India provider uses this to put the source document's E-Way Bill number on the
pass, where the operator would otherwise have to key it by hand.

The provider is exercised with a stub GST Settings and a plain source document,
because the `india_compliance` app that normally supplies them is not part of
this app's test site.
"""

from unittest import mock

import frappe
from frappe.tests.utils import FrappeTestCase

from gatepass_management.compliance import runner
from gatepass_management.compliance.base import GENERATED, PENDING, ComplianceResult
from gatepass_management.compliance.providers.india import (
	CHECK_E_WAY_BILL,
	IndiaComplianceProvider,
)
from gatepass_management.tests.utils import ensure_masters, make_gate_pass

EWAYBILL = "341000000001"


def result(status=GENERATED, document_no=EWAYBILL, populates="eway_bill_no"):
	return ComplianceResult(
		CHECK_E_WAY_BILL, status, label="E-Way Bill", document_no=document_no, populates=populates
	)


class TestPopulatedFields(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.masters = ensure_masters()

	def gate_pass(self, **fields):
		return make_gate_pass(self.masters, insert=False, **fields)

	def test_fills_an_empty_field(self):
		gp = self.gate_pass()
		runner.sync_to_gate_pass(gp, [result()])
		self.assertEqual(gp.eway_bill_no, EWAYBILL)

	def test_never_overwrites_what_the_operator_keyed(self):
		"""The number on the paper in the driver's hand may differ from the
		system's. Replacing it silently would hide the discrepancy."""
		gp = self.gate_pass(eway_bill_no="OPERATOR-KEYED")
		runner.sync_to_gate_pass(gp, [result()])
		self.assertEqual(gp.eway_bill_no, "OPERATOR-KEYED")

	def test_a_check_that_did_not_pass_writes_nothing(self):
		gp = self.gate_pass()
		runner.sync_to_gate_pass(gp, [result(status=PENDING, document_no="NOT-REAL")])
		self.assertFalse(gp.eway_bill_no)

	def test_no_document_number_writes_nothing(self):
		gp = self.gate_pass()
		runner.sync_to_gate_pass(gp, [result(document_no=None)])
		self.assertFalse(gp.eway_bill_no)

	def test_a_field_that_does_not_exist_is_ignored(self):
		"""A third-party provider naming a field this version lacks must not
		take the gate pass down with it."""
		gp = self.gate_pass()
		runner.sync_to_gate_pass(gp, [result(populates="no_such_field")])
		self.assertFalse(gp.get("no_such_field"))


class TestIndiaProviderNamesTheField(FrappeTestCase):
	def evaluate(self, **source):
		provider = IndiaComplianceProvider()
		source_doc = frappe._dict(
			doctype="Delivery Note", name="DN-STUB", grand_total=100000, owner=None, **source
		)
		with mock.patch.object(
			provider, "_gst_settings", return_value=frappe._dict(enable_e_waybill=1)
		):
			return provider._check_e_way_bill(None, source_doc)

	def test_a_generated_e_way_bill_populates_eway_bill_no(self):
		out = self.evaluate(ewaybill=EWAYBILL)
		self.assertEqual(out.status, GENERATED)
		self.assertEqual(out.document_no, EWAYBILL)
		self.assertEqual(out.populates, "eway_bill_no")

	def test_a_missing_one_populates_nothing(self):
		out = self.evaluate(ewaybill="")
		self.assertEqual(out.status, PENDING)
		self.assertIsNone(out.populates)
