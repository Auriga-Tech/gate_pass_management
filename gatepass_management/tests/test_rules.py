"""What the rules actually do.

`test_wiring` proves a rule is reachable. This proves it is right: that the
condition it describes is the condition it fires on, and that Block, Warn and
Ignore mean what the Settings page says.

Each test forces the rule under test to a known action, because the shipped
preset is Advisory where most rules only warn — asserting a block without
setting one tests the preset, not the rule.
"""

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, today

from gatepass_management.tests.utils import (
	ITEM,
	SUPPLIER,
	ensure_masters,
	make_gate_pass,
	rule_action,
	setting,
	violations_for,
)


class GatePassRuleTest(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.masters = ensure_masters()

	def pass_with(self, **fields):
		"""An unsaved Gate Pass. Most of these are invalid on purpose, and
		inserting one would raise the error the test is about to assert on."""
		rows = fields.pop("rows", None)
		return make_gate_pass(self.masters, rows=rows, insert=False, **fields)


class TestActionsMeanWhatTheySay(GatePassRuleTest):
	"""Block, Warn and Ignore, on one rule, so the engine itself is covered."""

	def setUp(self):
		# A future reference date: a condition that is simple and unambiguous.
		self.doc = self.pass_with(reference_date=add_days(today(), 5))

	def test_block_blocks(self):
		with rule_action("DOC-REF-DATE-FUTURE", "Block"):
			out = violations_for(self.doc)
		self.assertIn("DOC-REF-DATE-FUTURE", out["block"])
		self.assertNotIn("DOC-REF-DATE-FUTURE", out["warn"])

	def test_warn_records_but_does_not_block(self):
		with rule_action("DOC-REF-DATE-FUTURE", "Warn"):
			out = violations_for(self.doc)
		self.assertIn("DOC-REF-DATE-FUTURE", out["warn"])
		self.assertNotIn("DOC-REF-DATE-FUTURE", out["block"])

	def test_ignore_is_silent(self):
		with rule_action("DOC-REF-DATE-FUTURE", "Ignore"):
			out = violations_for(self.doc)
		self.assertNotIn("DOC-REF-DATE-FUTURE", out["block"] + out["warn"])

	def test_a_valid_document_fires_nothing(self):
		doc = self.pass_with(reference_date=today())
		with rule_action("DOC-REF-DATE-FUTURE", "Block"):
			out = violations_for(doc)
		self.assertNotIn("DOC-REF-DATE-FUTURE", out["block"] + out["warn"])


class TestDocumentRules(GatePassRuleTest):
	def test_returnable_must_be_outward(self):
		doc = self.pass_with(direction="In", is_returnable=1)
		out = violations_for(doc)
		self.assertIn("DOC-RETURNABLE-DIR", out["block"], "an inward pass may not be returnable")

	def test_return_date_cannot_precede_the_pass(self):
		doc = self.pass_with(
			direction="Out", is_returnable=1, expected_return_date=add_days(today(), -3)
		)
		with rule_action("DOC-RETURN-DATE", "Block"):
			out = violations_for(doc)
		self.assertIn("DOC-RETURN-DATE", out["block"])

	def test_backdating_beyond_the_window(self):
		with rule_action("DOC-BACKDATE", "Block", threshold=3):
			doc = self.pass_with(posting_date=add_days(today(), -10))
			self.assertIn("DOC-BACKDATE", violations_for(doc)["block"])

			within = self.pass_with(posting_date=add_days(today(), -1))
			self.assertNotIn("DOC-BACKDATE", violations_for(within)["block"])

	def test_items_required_unless_the_type_says_otherwise(self):
		with rule_action("DOC-ITEMS-REQUIRED", "Block"):
			doc = self.pass_with()
			doc.items = []
			self.assertIn("DOC-ITEMS-REQUIRED", violations_for(doc)["block"])

			# A visitor pass has nothing to list.
			visitor = self.pass_with()
			visitor.items = []
			visitor.gate_pass_type = "Visitor"
			self.assertNotIn("DOC-ITEMS-REQUIRED", violations_for(visitor)["block"])

	def test_security_officer_is_noticed_when_missing(self):
		doc = self.pass_with()
		doc.security_officer = None
		with rule_action("DOC-SECURITY-OFFICER", "Warn"):
			self.assertIn("DOC-SECURITY-OFFICER", violations_for(doc)["warn"])


class TestQuantityRules(GatePassRuleTest):
	def test_negative_quantity_always_blocks(self):
		"""QTY-NEGATIVE is HARD: it cannot be configured away, because a
		negative row would corrupt the consumption ledger."""
		doc = self.pass_with(rows=[{"item_name": "x", "uom": "Nos", "qty": -5}])
		self.assertIn("QTY-NEGATIVE", violations_for(doc)["block"])

	def test_zero_quantity(self):
		doc = self.pass_with(rows=[{"item_name": "x", "uom": "Nos", "qty": 0}])
		with rule_action("QTY-ZERO", "Block"):
			self.assertIn("QTY-ZERO", violations_for(doc)["block"])
		with rule_action("QTY-ZERO", "Ignore"):
			self.assertNotIn("QTY-ZERO", violations_for(doc)["block"])

	def test_conversion_factor_must_be_positive(self):
		doc = self.pass_with(rows=[{"item_name": "x", "uom": "Nos", "qty": 1}])
		doc.items[0].conversion_factor = 0
		self.assertIn("ITEM-CONVERSION", violations_for(doc)["block"])

	def test_item_required_unless_free_text(self):
		doc = self.pass_with(rows=[{"item_name": "x", "uom": "Nos", "qty": 1}])
		doc.items[0].is_non_stock = 0
		doc.items[0].item_code = None
		self.assertIn("ITEM-REQUIRED", violations_for(doc)["block"])

	def test_free_text_row_needs_a_name(self):
		doc = self.pass_with(rows=[{"uom": "Nos", "qty": 1}])
		doc.items[0].item_name = None
		self.assertIn("ITEM-NAME-REQUIRED", violations_for(doc)["block"])


class TestDiscrepancyRules(GatePassRuleTest):
	def test_the_quantities_must_balance(self):
		"""Accepted + short + damaged + rejected has to equal qty, or the pass
		is claiming a different amount arrived than it counted."""
		doc = self.pass_with(rows=[{"item_name": "x", "uom": "Nos", "qty": 10}])
		row = doc.items[0]
		row.accepted_qty, row.shortage_qty, row.damaged_qty, row.rejected_qty = 5, 1, 1, 1
		self.assertIn("DISC-BALANCE", violations_for(doc)["block"])

		row.accepted_qty = 7
		self.assertNotIn("DISC-BALANCE", violations_for(doc)["block"])

	def test_negative_discrepancy_always_blocks(self):
		doc = self.pass_with(rows=[{"item_name": "x", "uom": "Nos", "qty": 10}])
		doc.items[0].accepted_qty = 12
		doc.items[0].damaged_qty = -2
		self.assertIn("DISC-NEGATIVE", violations_for(doc)["block"])

	def test_reason_wanted_when_something_is_wrong(self):
		doc = self.pass_with(rows=[{"item_name": "x", "uom": "Nos", "qty": 10}])
		doc.items[0].accepted_qty = 8
		doc.items[0].damaged_qty = 2
		with rule_action("DISC-REASON", "Block"):
			self.assertIn("DISC-REASON", violations_for(doc)["block"])

	def test_notes_wanted_when_a_discrepancy_exists(self):
		doc = self.pass_with(rows=[{"item_name": "x", "uom": "Nos", "qty": 10}])
		doc.items[0].accepted_qty = 8
		doc.items[0].shortage_qty = 2
		doc.discrepancy_notes = None
		with rule_action("DISC-NOTES", "Block"):
			self.assertIn("DISC-NOTES", violations_for(doc)["block"])


class TestSubmitOnlyRules(GatePassRuleTest):
	"""Rules that must not pester someone filling in a draft."""

	def test_required_fields_only_bite_at_submit(self):
		doc = self.pass_with()
		doc.vehicle_number = ""

		with setting(require_vehicle=1):
			on_save = violations_for(doc, at_submit=False)
			at_submit = violations_for(doc, at_submit=True)

		self.assertEqual(
			[v for v in on_save["block"] if "FIELD" in v],
			[],
			"a draft must be allowed to be incomplete",
		)
		self.assertIn("FIELD-RULE", at_submit["block"])

	def test_required_field_satisfied(self):
		doc = self.pass_with(vehicle_number="MH-01-AA-1111")
		with setting(require_vehicle=1):
			self.assertNotIn("FIELD-RULE", violations_for(doc, at_submit=True)["block"])


class TestHardRulesCannotBeConfiguredAway(GatePassRuleTest):
	def test_hard_rule_blocks_even_when_the_preset_is_advisory(self):
		"""A HARD rule has no row in Settings, so there is nothing to relax."""
		from gatepass_management.rules import catalogue

		doc = self.pass_with(rows=[{"item_name": "x", "uom": "Nos", "qty": -1}])
		settings = frappe.get_single("Gate Pass Settings")
		self.assertNotIn(
			"QTY-NEGATIVE",
			[r.rule_code for r in settings.rules],
			"a HARD rule must not be offered as a setting",
		)
		self.assertIn("QTY-NEGATIVE", violations_for(doc)["block"])
