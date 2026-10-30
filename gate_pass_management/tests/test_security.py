"""The paths Frappe's security audit flagged: stored templates, messages built from
exceptions, and SQL assembled from strings.

Each is tested by what it must refuse or produce, not by reading the code, so a
later edit that reopens one fails here.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from gate_pass_management.tests.utils import ensure_masters, make_gate_pass, setting
from gate_pass_management.utils import notify, tracking

# What someone with write access to Gate Pass Settings might try to store.
HOSTILE_TEMPLATES = (
	"{{ ''.__class__.__mro__ }}",
	"{{ config }}",
	"{{ 7 * 7 }}",
	"{{ party_code | upper }}",
	"{{ party_code.__class__ }}",
	"{% for i in range(5) %}x{% endfor %}",
	"{# comment #}{{ party }}",
	"{{ frappe.db.get_value('User', 'Administrator', 'password') }}",
)


class TestTrackingTemplates(FrappeTestCase):
	def test_the_default_template_renders(self):
		context = {"party_code": "ACM", "reference_no": "INV-9"}
		self.assertEqual(tracking.render("{{ party_code }}/{{ reference_no }}", context), "ACM/INV-9")

	def test_spacing_inside_the_braces_does_not_matter(self):
		self.assertEqual(tracking.render("{{party}}-{{   reference_no  }}", {"party": "P", "reference_no": "R"}), "P-R")

	def test_a_missing_value_is_blank_not_an_error(self):
		self.assertEqual(tracking.render("{{ party_code }}/{{ reference_no }}", {"party_code": "ACM"}), "ACM/")

	def test_every_documented_field_can_be_used(self):
		template = "-".join("{{ %s }}" % f for f in tracking.FIELDS)
		context = {f: f.upper() for f in tracking.FIELDS}
		self.assertEqual(tracking.render(template, context), "-".join(f.upper() for f in tracking.FIELDS))

	def test_hostile_templates_are_refused_and_never_evaluated(self):
		for template in HOSTILE_TEMPLATES:
			with self.subTest(template=template):
				with self.assertRaises(ValueError):
					tracking.render(template, {"party_code": "ACM", "party": "P"})

	def test_the_error_names_the_unknown_field_and_the_allowed_ones(self):
		with self.assertRaises(ValueError) as ctx:
			tracking.check("{{ nonsense }}")
		message = str(ctx.exception)
		self.assertIn("nonsense", message)
		self.assertIn("reference_no", message)


class TestTrackingTemplatesInSettings(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.masters = ensure_masters()

	def _save_template(self, template):
		settings = frappe.get_single("Gate Pass Settings")
		settings.enable_tracking_id = 1
		settings.tracking_id_template = template
		settings.save(ignore_permissions=True)

	def test_settings_refuse_a_hostile_template(self):
		for template in HOSTILE_TEMPLATES[:4]:
			with self.subTest(template=template):
				with self.assertRaises(frappe.ValidationError) as ctx:
					self._save_template(template)
				self.assertIn("not valid", str(ctx.exception))

	def test_settings_accept_a_good_template(self):
		before = frappe.get_single("Gate Pass Settings")
		restore = (before.enable_tracking_id, before.tracking_id_template)
		try:
			self._save_template("{{ party_code }}/{{ reference_no }}")
		finally:
			frappe.db.set_value("Gate Pass Settings", None, {"enable_tracking_id": restore[0], "tracking_id_template": restore[1]})
			frappe.clear_cache()

	def test_a_gate_pass_takes_its_tracking_id_from_the_template(self):
		with setting(enable_tracking_id=1, tracking_id_template="TRK-{{ reference_no }}-{{ direction }}"):
			gp = make_gate_pass(self.masters, reference_no="R-77")
		self.assertEqual(gp.tracking_id, "TRK-R-77-In")

	def test_a_hostile_template_already_stored_cannot_be_used_to_make_a_pass(self):
		"""Stored before this rule, or written around the form: still refused."""
		with setting(enable_tracking_id=1, tracking_id_template="{{ ''.__class__.__mro__ }}"):
			with self.assertRaises(frappe.ValidationError) as ctx:
				make_gate_pass(self.masters)
		self.assertIn("could not be rendered", str(ctx.exception))


class TestEmailTemplates(FrappeTestCase):
	"""Notifications render the configured Email Template through Frappe's own path."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.masters = ensure_masters()
		if not frappe.db.exists("Email Template", "_GPTEST Notify"):
			frappe.get_doc(
				{
					"doctype": "Email Template",
					"name": "_GPTEST Notify",
					"subject": "Pass {{ name }} for {{ doc.party }}",
					"use_html": 0,
					"response": "<p>{{ intro }} Party: {{ party }} / {{ doc.party }}</p>",
				}
			).insert(ignore_permissions=True)

	def test_the_template_sees_the_document_and_the_intro(self):
		from unittest import mock

		gp = make_gate_pass(self.masters)
		settings = frappe._dict(email_template="_GPTEST Notify", enable_whatsapp=0)

		with mock.patch.object(notify, "_recipients", return_value=["gate@example.com"]), mock.patch(
			"frappe.sendmail"
		) as sendmail:
			notify._send(settings, subject="fallback subject", intro="Submitted.", doc=gp)

		self.assertTrue(sendmail.called, "the notification should have been sent")
		sent = sendmail.call_args.kwargs
		self.assertEqual(sent["subject"], f"Pass {gp.name} for {gp.party}")
		self.assertIn("Submitted.", sent["message"])
		self.assertIn(f"Party: {gp.party} / {gp.party}", sent["message"])

	def test_without_a_template_the_default_body_is_sent(self):
		from unittest import mock

		gp = make_gate_pass(self.masters)
		with mock.patch.object(notify, "_recipients", return_value=["gate@example.com"]), mock.patch(
			"frappe.sendmail"
		) as sendmail:
			notify._send(frappe._dict(email_template=None, enable_whatsapp=0), "Plain subject", "Hello.", gp)
		self.assertEqual(sendmail.call_args.kwargs["subject"], "Plain subject")


class TestNoRawSqlInTheLockOrThePatch(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.masters = ensure_masters()

	def test_the_ledger_lock_takes_a_real_row_lock(self):
		from gate_pass_management import ledger
		from gate_pass_management.tests.utils import make_purchase_order, ITEM

		po = make_purchase_order(self.masters, [(ITEM, 5)])
		ledger._lock_source_documents("Purchase Order", [po.name, po.name, "NO-SUCH-ORDER", ""])

	def test_the_ledger_lock_does_not_trust_the_doctype_name(self):
		"""A hostile name is quoted as one table name, so it finds no table and fails
		loudly; it does not run as SQL."""
		from gate_pass_management import ledger

		with self.assertRaises(Exception):
			ledger._lock_source_documents("Purchase Order`; select sleep(30); -- ", ["x"])

	def test_the_module_rename_patch_updates_by_value(self):
		from gate_pass_management.patches.v1_0 import rename_module_to_gate_pass_management as patch

		name = frappe.db.get_value("Print Format", {"doc_type": "Gate Pass"}, "name")
		frappe.db.set_value("Print Format", name, "module", "Old Module Name", update_modified=False)
		original = (patch.OLD, patch.NEW)
		patch.OLD, patch.NEW = "Old Module Name", "Gate Pass Management"
		try:
			patch._rename("Print Format", "module")
		finally:
			patch.OLD, patch.NEW = original
		self.assertEqual(frappe.db.get_value("Print Format", name, "module"), "Gate Pass Management")
