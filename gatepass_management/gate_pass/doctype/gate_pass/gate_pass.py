"""The Gate Pass document.

A gate pass records a physical movement across a boundary and reconciles it
against the commercial documents ERPNext already owns.

It is a CONTROL document, not a stock document. It never writes a Stock Ledger
Entry, never touches valuation, and never creates a GL Entry. That constraint is
what makes this app safe to install on a live ERP, and nothing in this file may
violate it.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, get_link_to_form, getdate, now_datetime, today

from gatepass_management import ledger
from gatepass_management.compliance import runner as compliance
from gatepass_management.rules.engine import RuleContext
from gatepass_management.utils import guards
from gatepass_management.utils.logger import get_logger


class GatePass(Document):
	# --------------------------------------------------------------- hooks

	def before_insert(self):
		self._set_security_officer()
		self._render_tracking_id()
		self._seed_checklist()
		self._seed_charges()

	def validate(self):
		self._derive_direction()
		self._resolve_party()
		self._apply_qty_policy()
		self._compute_row_values()
		self._compute_totals()
		self._compute_weights()
		self._refresh_compliance()
		self._set_status()
		self.run_rules()

	def before_submit(self):
		self._stamp_timestamps()
		self.enforcement_mode = frappe.get_cached_value(
			"Gate Pass Settings", None, "enforcement_preset"
		)
		self.run_rules(at_submit=True)

	def on_submit(self):
		self._log("Submitted")
		self._log("Entered" if self.direction == "In" else "Exited")
		self._set_status()
		self.db_set("status", self.status, update_modified=False)
		self._create_auto_target()

	def before_cancel(self):
		self._check_cancellation_policy()

	def on_cancel(self):
		self.flags.ignore_links = True
		self.status = "Cancelled"
		self._log("Cancelled")

	def on_update_after_submit(self):
		self._compute_totals()
		self._set_status()

	def before_save(self):
		if self.is_new():
			self._log_pending = "Created"

	def on_update(self):
		if getattr(self, "_log_pending", None):
			self._log(self._log_pending)
			self._log_pending = None

	# ------------------------------------------------------------ defaults

	def _set_security_officer(self):
		"""Who was on the gate. Filled automatically so it is never blank by accident."""
		if self.security_officer:
			return
		employee = frappe.db.get_value(
			"Employee", {"user_id": frappe.session.user, "status": "Active"}, "name"
		)
		if employee:
			self.security_officer = employee

	def _render_tracking_id(self):
		"""Render once, at creation, then freeze.

		A tracking ID that changes is not a tracking ID. Rendering failure raises
		rather than silently producing an empty string — the prior implementation
		fell back to "" and nobody noticed until reconciliation.
		"""
		settings = guards.get_settings()
		if not settings.enable_tracking_id or self.tracking_id:
			return

		if settings.tracking_id_inherit_field and self.source_doctype and self.source_document:
			inherited = frappe.db.get_value(
				self.source_doctype, self.source_document, settings.tracking_id_inherit_field
			)
			if inherited:
				self.tracking_id = inherited
				return

		template = (settings.tracking_id_template or "").strip()
		if not template:
			return

		context = {
			"party_code": self._party_code(),
			"party": self.party or "",
			"reference_no": (self.reference_no or "").strip(),
			"vehicle_number": (self.vehicle_number or "").strip(),
			"posting_date": self.posting_date,
			"direction": self.direction,
		}
		try:
			self.tracking_id = frappe.render_template(template, context).strip()
		except Exception as exc:
			frappe.throw(
				_("Tracking ID template could not be rendered: {0}").format(exc),
				title=_("Check Gate Pass Settings"),
			)

	def _party_code(self) -> str:
		if not self.party_type or not self.party:
			return ""
		for fieldname in ("gate_pass_party_code", "supplier_code", "customer_code"):
			if frappe.get_meta(self.party_type).has_field(fieldname):
				value = frappe.db.get_value(self.party_type, self.party, fieldname)
				if value:
					return value
		return self.party

	def _seed_checklist(self):
		"""Populate required-document rows from the source flow's checklist."""
		if self.documents:
			return
		config = self.source_config
		if not config:
			return
		for row in config.get("checklist") or []:
			if row.applies_to_direction not in ("Both", None, "", self.direction):
				continue
			self.append(
				"documents",
				{
					"document_name": row.document_name,
					"is_mandatory": row.is_mandatory,
				},
			)

	def _seed_charges(self):
		settings = guards.get_settings()
		if not settings.enable_charges or self.charges:
			return
		for row in settings.get("charge_types") or []:
			if not row.is_active:
				continue
			if row.applies_to_direction not in ("Both", None, "", self.direction):
				continue
			self.append(
				"charges",
				{
					"charge_type": row.charge_type,
					"is_mandatory": row.is_mandatory,
					"amount": row.default_amount,
					"paid_by": row.paid_by,
				},
			)

	# ------------------------------------------------------------ derived

	@property
	def source_config(self):
		if not self.source_type:
			return None
		if not hasattr(self, "_source_config"):
			self._source_config = frappe.get_cached_doc("Gate Pass Source", self.source_type)
		return self._source_config

	def _derive_direction(self):
		"""Direction follows the source flow.

		The operator picks the document they are holding; the direction is a
		consequence of that, not a separate decision they can get wrong.
		"""
		config = self.source_config
		if config and config.direction:
			self.direction = config.direction
			self.source_doctype = config.source_doctype
			self.source_sub_type = config.sub_type

		documents = {r.source_document for r in self.items if r.source_document}
		self.is_multi_source = 1 if len(documents) > 1 else 0
		if len(documents) == 1:
			self.source_document = next(iter(documents))
		elif not documents:
			self.source_document = None

	def _resolve_party(self):
		if self.party_type and self.party:
			meta = frappe.get_meta(self.party_type)
			for fieldname in (f"{frappe.scrub(self.party_type)}_name", "full_name", "name"):
				if meta.has_field(fieldname):
					self.party_name = frappe.db.get_value(self.party_type, self.party, fieldname)
					break
		if self.address:
			from frappe.contacts.doctype.address.address import get_address_display

			self.address_display = get_address_display(self.address)

	def _apply_qty_policy(self):
		"""Enforce the source flow's quantity policy.

		Outward dispatch against an invoice must not be restatable at the gate:
		the guard verifies what leaves, they do not get to change the number.
		Any difference is recorded as shortage, damage, or rejection instead.
		"""
		config = self.source_config
		if not config or config.qty_policy not in ("Locked to Source", "Editable within Tolerance"):
			return

		for row in self.items:
			if not row.source_row:
				continue
			if config.qty_policy == "Locked to Source" and flt(row.qty) != flt(row.source_qty):
				row.qty = flt(row.source_qty)

	def _compute_row_values(self):
		for row in self.items:
			row.conversion_factor = flt(row.conversion_factor) or 1
			row.stock_qty = flt(row.qty) * flt(row.conversion_factor)
			row.amount = flt(row.qty) * flt(row.rate)

			# Accepted defaults to the full quantity; discrepancy rows reduce it.
			explicit = flt(row.shortage_qty) + flt(row.damaged_qty) + flt(row.rejected_qty)
			if not flt(row.accepted_qty) and not explicit:
				row.accepted_qty = flt(row.qty)
			elif explicit and not flt(row.accepted_qty):
				row.accepted_qty = flt(row.qty) - explicit

			if row.item_code and not row.stock_uom:
				row.stock_uom = frappe.db.get_value("Item", row.item_code, "stock_uom")

	def _compute_totals(self):
		self.total_qty = sum(flt(r.qty) for r in self.items)
		self.total_accepted_qty = sum(flt(r.accepted_qty) for r in self.items)
		self.total_shortage_qty = sum(flt(r.shortage_qty) for r in self.items)
		self.total_damaged_qty = sum(flt(r.damaged_qty) for r in self.items)
		self.total_rejected_qty = sum(flt(r.rejected_qty) for r in self.items)
		self.total_amount = sum(flt(r.amount) for r in self.items)
		self.total_packages = sum(cint(r.packages) for r in self.items)
		self.total_charges = sum(flt(c.amount) for c in self.charges)

		self.has_discrepancy = 1 if (
			self.total_shortage_qty or self.total_damaged_qty or self.total_rejected_qty
		) else 0

		self.processed_qty = sum(flt(r.qty) for r in self.references if r.link_type == "Target")
		self.per_processed = compute_per_processed(self.processed_qty, self.total_accepted_qty)

	def _compute_weights(self):
		if self.gross_weight or self.tare_weight:
			self.net_weight = flt(self.gross_weight) - flt(self.tare_weight)

	def _stamp_timestamps(self):
		stamp = now_datetime()
		if self.direction == "In" and not self.entry_datetime:
			self.entry_datetime = stamp
		if self.direction == "Out" and not self.exit_datetime:
			self.exit_datetime = stamp
		if self.entry_datetime and self.exit_datetime:
			delta = getdate(self.exit_datetime), getdate(self.entry_datetime)
			self.turnaround_minutes = int(
				(frappe.utils.get_datetime(self.exit_datetime)
				 - frappe.utils.get_datetime(self.entry_datetime)).total_seconds() / 60
			)

	# ----------------------------------------------------------- compliance

	def _refresh_compliance(self):
		settings = guards.get_settings()
		if not settings.enable_compliance_checks:
			self.compliance_status = "Not Applicable"
			return
		results = compliance.evaluate(self, self.source_config)
		compliance.sync_to_gate_pass(self, results)

	# ---------------------------------------------------------------- status

	def _set_status(self):
		self.status = derive_status(self)

	# ----------------------------------------------------------------- rules

	def run_rules(self, at_submit: bool = False):
		from gatepass_management.gate_pass.doctype.gate_pass import validations

		ctx = RuleContext(self, self.source_config)
		validations.run(self, ctx, at_submit=at_submit)
		ctx.raise_if_blocked()

	# ------------------------------------------------------------- lifecycle

	def _check_cancellation_policy(self):
		policy = frappe.get_cached_value("Gate Pass Settings", None, "cancellation_policy")
		submitted = [r for r in self.references if r.link_type == "Target" and self._is_submitted(r)]

		if not submitted:
			return

		if policy == "Block if Linked Documents Exist":
			links = "".join(
				f"<li>{_(r.reference_doctype)}: "
				f"{get_link_to_form(r.reference_doctype, r.reference_name)}</li>"
				for r in submitted
			)
			frappe.throw(
				_(
					"This Gate Pass cannot be cancelled while these submitted documents "
					"are linked to it:<ul>{0}</ul>Cancel them first."
				).format(links),
				title=_("Linked Documents Exist"),
			)

		if policy == "Cascade Cancel Targets":
			from gatepass_management.targets.cancel import cascade_cancel

			cascade_cancel(self, submitted)

		# "Allow and Unlink" falls through; targets.guards clears the link.

	def _is_submitted(self, reference) -> bool:
		if not reference.reference_doctype or not reference.reference_name:
			return False
		return (
			frappe.db.get_value(reference.reference_doctype, reference.reference_name, "docstatus")
			== 1
		)

	def _create_auto_target(self):
		config = self.source_config
		if not config or config.target_creation_mode != "Auto on Submit":
			return

		from gatepass_management.targets.create import create_target

		# Deliberately NOT wrapped in a try/except that continues. A gate pass
		# configured to create its receipt automatically has not done its job if
		# the receipt is missing, and reporting success in that state is how the
		# implementations this app replaces produced phantom receipts.
		create_target(self.name, config.target_doctype, raise_on_error=True)

	# --------------------------------------------------------------- helpers

	def _log(self, event: str, **kwargs):
		from gatepass_management.gate_pass.doctype.gate_pass_event_log.api import log_event

		log_event(gate_pass=self.name, event=event, **kwargs)

	def set_indicator(self):
		pass


# ===========================================================================
# Shared computations — one definition, so the three call sites cannot drift.
# ===========================================================================


def compute_per_processed(processed_qty, accepted_qty) -> float:
	"""Percentage of the gate pass that has reached a target document.

	Measured against ACCEPTED quantity, not the gate-passed quantity. Only what
	the gate physically took in can ever be received, so a pass with any
	shortage or damage could never reach 100% if the denominator were the
	paperwork figure — it would sit on the store manager's worklist for ever,
	claiming work that does not exist.
	"""
	accepted = flt(accepted_qty)
	if not accepted:
		return 0.0
	return flt(flt(processed_qty) / accepted * 100, 6)


# ===========================================================================
# Status derivation — pure function, unit tested against a table of inputs.
# ===========================================================================


def derive_status(doc) -> str:
	if doc.docstatus == 2:
		return "Cancelled"
	if doc.docstatus == 0:
		return "Draft"

	if doc.direction == "In":
		if not doc.entry_datetime:
			return "At Gate"
		if flt(doc.per_processed) >= 100:
			return "Completed"
		if flt(doc.per_processed) > 0:
			return "Partially Processed"
		return "Inside"

	# Outward
	if not doc.exit_datetime:
		return "At Gate"

	if not doc.is_returnable:
		if doc.source_type and flt(doc.total_accepted_qty) and flt(doc.per_processed) < 100:
			return "Partially Processed" if flt(doc.per_processed) > 0 else "Inside"
		return "Completed"

	returned = flt(doc.returned_qty)
	total = flt(doc.total_qty)

	if returned >= total and total:
		return "Returned"
	if returned > 0:
		return "Partially Returned"
	if doc.expected_return_date and getdate(doc.expected_return_date) < getdate(today()):
		return "Overdue Return"
	return "Pending Return"
