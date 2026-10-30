"""The shipped standard records, and the identity they are keyed on.

`Gate Pass Source` is named from `flow_code`, not from `source_name`. That is
the whole point of this module. The display label is prose, it has been reworded
once already, and every gate pass stores the record name in `source_type` — so
if the label were the key, rewording it would insert twelve new flows, orphan
the twelve old ones, and break `source_type` on every pass ever created.

Nothing about that failure shows up in a behavioural test, because each
individual flow still works afterwards. It only shows up as a duplicate on an
upgrade, on a customer's site. So it is asserted here instead.
"""

import copy

import frappe
from frappe.tests.utils import FrappeTestCase

from gate_pass_management.setup import fixtures

DASHES = ("—", "–")  # em dash, en dash


class TestFlowCodes(FrappeTestCase):
	def test_every_shipped_flow_has_a_code(self):
		missing = [s["source_name"] for s in fixtures.STANDARD_SOURCES if not s.get("flow_code")]
		self.assertEqual(missing, [], "flows with no flow_code:\n  " + "\n  ".join(missing))

	def test_codes_are_unique(self):
		codes = [s["flow_code"] for s in fixtures.STANDARD_SOURCES]
		self.assertEqual(len(codes), len(set(codes)), f"duplicate flow codes in {codes}")

	def test_the_record_is_named_after_its_code(self):
		"""If `autoname` ever drifts back to the label, this fails."""
		self.assertEqual(
			frappe.get_meta("Gate Pass Source").autoname,
			"field:flow_code",
			"Gate Pass Source must be keyed on flow_code, never on the display label",
		)
		for spec in fixtures.STANDARD_SOURCES:
			with self.subTest(flow=spec["flow_code"]):
				self.assertTrue(
					frappe.db.exists("Gate Pass Source", spec["flow_code"]),
					f"{spec['flow_code']} is not installed under its own code",
				)

	def test_no_dash_characters_in_a_record_name(self):
		"""A record name reaches URLs, support tickets and `source_type` values.

		An em dash there is awkward to type and to search for. In prose it is
		correct and this says nothing about it.
		"""
		bad = [
			s["flow_code"]
			for s in fixtures.STANDARD_SOURCES
			if any(d in s["flow_code"] for d in DASHES)
		]
		self.assertEqual(bad, [], f"flow codes containing an em/en dash: {bad}")


class TestRewordingALabelIsFree(FrappeTestCase):
	"""The regression this design exists to prevent."""

	def test_a_reworded_label_updates_in_place(self):
		before = frappe.db.count("Gate Pass Source")
		target = fixtures.STANDARD_SOURCES[0]
		code = target["flow_code"]

		patched = copy.deepcopy(fixtures.STANDARD_SOURCES)
		patched[0]["source_name"] = "Totally Different Wording"

		original = fixtures.STANDARD_SOURCES
		fixtures.STANDARD_SOURCES = patched
		try:
			fixtures.seed_sources()
		finally:
			fixtures.STANDARD_SOURCES = original

		self.assertEqual(
			frappe.db.count("Gate Pass Source"),
			before,
			"rewording a label must not create a flow — it is not the identity",
		)
		self.assertEqual(
			frappe.db.get_value("Gate Pass Source", code, "source_name"),
			"Totally Different Wording",
			"the new label must reach existing sites",
		)

	def test_seeding_twice_changes_nothing(self):
		before = frappe.db.count("Gate Pass Source")
		fixtures.seed_sources()
		self.assertEqual(frappe.db.count("Gate Pass Source"), before)


class TestShippedPurposes(FrappeTestCase):
	"""The Purpose field is a link, so with no records behind it the dropdown is empty."""

	def test_names_are_unique_and_url_safe(self):
		names = [p[0] for p in fixtures.STANDARD_PURPOSES]
		self.assertEqual(len(names), len(set(names)), "duplicate purpose names")
		bad = [n for n in names if "/" in n or any(d in n for d in DASHES)]
		self.assertEqual(bad, [], "a slash breaks form URLs; dashes are banned by our standard")

	def test_values_are_valid_for_the_doctype(self):
		meta = frappe.get_meta("Gate Pass Purpose")
		directions = meta.get_field("applies_to_direction").options.split("\n")
		types = meta.get_field("default_gate_pass_type").options.split("\n")
		for name, direction, pass_type, _note in fixtures.STANDARD_PURPOSES:
			self.assertIn(direction, directions, name)
			self.assertIn(pass_type, types, name)

	def test_seeding_creates_every_purpose_and_is_repeatable(self):
		frappe.db.delete("Gate Pass Purpose")
		fixtures.seed_purposes()
		fixtures.seed_purposes()
		self.assertEqual(
			frappe.db.count("Gate Pass Purpose"), len(fixtures.STANDARD_PURPOSES)
		)

	def test_migrate_fills_purposes_on_a_site_that_has_reasons_but_no_purposes(self):
		"""erp16 and any earlier install: reasons exist, purposes do not."""
		from gate_pass_management.setup import install

		frappe.db.delete("Gate Pass Purpose")
		install.after_migrate()
		self.assertEqual(
			frappe.db.count("Gate Pass Purpose"), len(fixtures.STANDARD_PURPOSES)
		)
