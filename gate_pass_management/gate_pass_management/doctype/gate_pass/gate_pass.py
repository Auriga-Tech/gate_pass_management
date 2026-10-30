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
from frappe.query_builder.functions import Max, Sum
from frappe.utils import add_days, cint, flt, get_link_to_form, getdate, now_datetime, today

from gate_pass_management import ledger
from gate_pass_management.compliance import runner as compliance
from gate_pass_management.rules.engine import RuleContext
from gate_pass_management.utils import guards, tracking
from gate_pass_management.utils.logger import get_logger


# Fields `_compute_totals` and `_set_status` derive, which a change after submission can move.
DERIVED_AFTER_SUBMIT = (
	"total_qty", "total_accepted_qty", "total_shortage_qty", "total_damaged_qty",
	"total_rejected_qty", "total_amount", "total_packages", "total_charges",
	"has_discrepancy", "processed_qty", "per_processed", "status", "return_status",
)


class GatePass(Document):
	# --------------------------------------------------------------- hooks

	def before_naming(self):
		"""The series follows the direction.

		Naming runs before `validate`, so the direction cannot wait to be
		derived there: a pass built from a flow takes the flow's direction, as
		`_derive_direction` will, and any other pass takes what was chosen.
		"""
		series = series_for_direction(self._naming_direction())
		if series:
			self.naming_series = series

	def _naming_direction(self) -> str | None:
		if self.source_type:
			direction = frappe.db.get_value("Gate Pass Source", self.source_type, "direction")
			if direction:
				return direction
		return self.direction

	def before_insert(self):
		self._set_security_officer()
		self._render_tracking_id()
		self._default_return_date()
		self._seed_checklist()
		self._seed_charges()

	def validate(self):
		self._check_amend_allowed()
		self.derive_fields()
		self._check_purpose()
		self._check_party_links()
		self.run_rules()

	def derive_fields(self):
		"""Fill in everything the rules are then judged against.

		Separate from `validate` so the rules can be run against a document
		without saving it — several of them read a derived field such as
		`has_discrepancy` or `accepted_qty`, and a test that skipped this step
		would be checking a half-built document rather than the rule.
		"""
		self._check_party_type_allowed()
		self._apply_party_defaults()
		self._derive_direction()
		self._resolve_party()
		self._apply_qty_policy()
		self._compute_row_values()
		self._compute_totals()
		self._compute_weights()
		self._refresh_compliance()
		self._set_status()

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
		# Frappe has already written the row; a plain assignment would not reach it.
		self.db_set(
			{"status": self.status, "return_status": self.return_status}, update_modified=False
		)
		self._sync_returnable_origin()
		self._create_auto_target()

		from gate_pass_management.utils import notify

		notify.on_gate_pass_submit(self)

	def before_cancel(self):
		self._check_cancellation_policy()

	def on_cancel(self):
		self.flags.ignore_links = True
		# Written after the row, so it has to be stored explicitly: without this a
		# cancelled pass kept the status it had (Inside) in the database.
		self.db_set("status", "Cancelled", update_modified=False)
		self._log("Cancelled")
		# A cancelled return leg gives the quantity back to the pass it closed.
		self._sync_returnable_origin()

	def on_update_after_submit(self):
		"""Recompute what a post-submit change moves, and store it.

		This runs after Frappe has written the document, and the fields below are
		not all `allow_on_submit`, so they are written with `db_set` rather than
		by assignment: assignment left the stored totals stale, and a discrepancy
		recorded after submission never reached `has_discrepancy`.
		"""
		self._compute_totals()
		self._set_status()
		self.db_set({f: self.get(f) for f in DERIVED_AFTER_SUBMIT}, update_modified=False)

	def before_save(self):
		if self.is_new():
			self.flags.log_pending = "Created"

	def on_update(self):
		# A flag, not a field: it only carries a message from before_save to here.
		if self.flags.log_pending:
			self._log(self.flags.log_pending)
			self.flags.log_pending = None

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
			self.tracking_id = tracking.render(template, context)
		except ValueError as exc:
			frappe.throw(
				_("Tracking ID template could not be rendered: {0}").format(str(exc)),
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

	def _default_return_date(self):
		"""A returnable pass with no due date can never become overdue.

		`flag_overdue_returns` selects on `expected_return_date < today`, and a
		NULL never matches that, so a pass saved without a date would sit as
		Pending Return for ever and never be chased. Fill it from the configured
		window rather than leaving a silent hole.
		"""
		if self.direction != "Out" or not self.is_returnable or self.expected_return_date:
			return
		days = cint(guards.get_settings().default_return_days)
		if days > 0:
			self.expected_return_date = add_days(self.posting_date or today(), days)

	def _sync_returnable_origin(self):
		"""Keep the outward pass this one returns against up to date.

		A return leg is a gate pass whose source is the outward pass. Nothing
		else writes `returned_qty`, `actual_return_date` or `return_status`, so
		without this a returnable pass stays Pending Return no matter how much
		comes back. Recomputed from the submitted legs on every submit and
		cancel, so it is always the sum rather than a running total that can
		drift.
		"""
		if self.source_doctype != "Gate Pass" or not self.source_document:
			return
		if not frappe.db.exists("Gate Pass", self.source_document):
			return

		origin = frappe.get_doc("Gate Pass", self.source_document)
		if origin.docstatus != 1 or not origin.is_returnable:
			return

		GP = frappe.qb.DocType("Gate Pass")
		GPI = frappe.qb.DocType("Gate Pass Item")
		row = (
			frappe.qb.from_(GPI)
			.inner_join(GP)
			.on(GP.name == GPI.parent)
			.select(Sum(GPI.qty).as_("returned"), Max(GP.posting_date).as_("last_date"))
			.where(GP.docstatus == 1)
			.where(GP.source_doctype == "Gate Pass")
			.where(GP.source_document == origin.name)
		).run(as_dict=True)

		returned = flt(row[0].returned) if row else 0.0
		last_date = row[0].last_date if row else None

		origin.db_set("returned_qty", returned, update_modified=False)
		origin.db_set("actual_return_date", last_date if returned else None, update_modified=False)
		origin.reload()
		origin.db_set("return_status", derive_return_status(origin), update_modified=False)
		origin.reload()
		status = derive_status(origin)
		# `auto_close_on_full_return`: a fully returned pass is finished business,
		# so close it rather than leaving it on the Pending Returnable report.
		if status == "Returned" and cint(guards.get_settings().auto_close_on_full_return):
			status = "Closed"
		origin.db_set("status", status, update_modified=False)

		from gate_pass_management.gate_pass_management.doctype.gate_pass_event_log.api import log_event

		log_event(
			gate_pass=origin.name,
			event="Return Recorded",
			reference_doctype="Gate Pass",
			reference_name=self.name,
			qty_delta=returned,
			message=_("{0} of {1} returned.").format(flt(returned), flt(origin.total_qty)),
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

	def _apply_party_defaults(self):
		"""`default_party_type` and `allow_gate_pass_without_party` were both inert."""
		settings = guards.get_settings()
		if not self.party_type and settings.default_party_type:
			self.party_type = settings.default_party_type
		if not self.party and not cint(settings.allow_gate_pass_without_party):
			if self.gate_pass_type not in ("Visitor", "Vehicle Only"):
				frappe.throw(
					_("Select a Party. Gate passes without a party are disabled in "
					  "Gate Pass Settings."),
					title=_("Party required"),
				)

	def _check_party_links(self):
		"""The address and contact must belong to the party they sit under.

		Judged when one of the four fields has changed, so a pass saved before
		this rule keeps whatever it had.
		"""
		if not (self.party_type and self.party):
			return
		watched = ("party_type", "party", "address", "contact_person")
		if not (self.is_new() or any(self.has_value_changed(f) for f in watched)):
			return

		for fieldname, doctype in (("address", "Address"), ("contact_person", "Contact")):
			name = self.get(fieldname)
			if name and not frappe.db.exists(
				"Dynamic Link",
				{"parenttype": doctype, "parent": name, "link_doctype": self.party_type, "link_name": self.party},
			):
				frappe.throw(
					_("{0} {1} is not linked to {2} {3}. Choose one of this party's own, or link it "
					  "to the party on the {0} first.").format(
						_(doctype), frappe.bold(name), _(self.party_type), frappe.bold(self.party)
					),
					title=_("Not this party's {0}").format(_(doctype)),
				)

	def _check_purpose(self):
		"""The purpose must be live and must fit the direction.

		Only judged when the purpose or the direction has just changed, so a pass
		saved long ago keeps its purpose after the master is later retired.
		"""
		if not self.purpose:
			return
		purpose_changed = self.is_new() or self.has_value_changed("purpose")
		if not (purpose_changed or self.has_value_changed("direction")):
			return

		direction, active = frappe.db.get_value(
			"Gate Pass Purpose", self.purpose, ["applies_to_direction", "is_active"]
		) or (None, 1)

		if purpose_changed and not cint(active):
			frappe.throw(
				_("Purpose {0} is no longer active. Choose another.").format(frappe.bold(self.purpose)),
				title=_("Purpose inactive"),
			)
		if direction not in ("Both", None, "", self.direction):
			frappe.throw(
				_("Purpose {0} is for {1} passes, but this pass is {2}.").format(
					frappe.bold(self.purpose), _(direction), _(self.direction)
				),
				title=_("Purpose does not fit"),
			)

	def _check_party_type_allowed(self):
		"""Gate Pass Settings > Allowed Party Types. An empty list restricts nothing."""
		allowed = allowed_party_types()
		if self.party_type and allowed and self.party_type not in allowed:
			frappe.throw(
				_("{0} is not an allowed Party Type. Choose one of: {1}.").format(
					frappe.bold(_(self.party_type)), ", ".join(_(p) for p in allowed)
				),
				title=_("Party Type not allowed"),
			)

	def _check_amend_allowed(self):
		"""`allow_amend` shipped in Settings and nothing read it."""
		if self.amended_from and not cint(guards.get_settings().allow_amend):
			frappe.throw(
				_("Amending a Gate Pass is disabled in Gate Pass Settings. "
				  "Create a new one instead."),
				title=_("Amend not allowed"),
			)

	def _resolve_party(self):
		if self.party_type and self.party:
			meta = frappe.get_meta(self.party_type)
			for fieldname in (f"{frappe.scrub(self.party_type)}_name", "full_name", "name"):
				if meta.has_field(fieldname):
					self.party_name = frappe.db.get_value(self.party_type, self.party, fieldname)
					break
		if self.contact_person and not self.contact_mobile:
			mobile, phone = frappe.db.get_value("Contact", self.contact_person, ["mobile_no", "phone"]) or (None, None)
			self.contact_mobile = mobile or phone
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
			# Default only when it was never filled in. `or 1` also rewrote an
			# explicit 0, which silently repaired the exact value ITEM-CONVERSION
			# exists to reject — leaving that rule unable to fire at all.
			if row.conversion_factor in (None, ""):
				row.conversion_factor = 1
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
		settings = guards.get_settings()
		self.total_packages = (
			sum(cint(r.packages) for r in self.items) if cint(settings.enable_packages) else 0
		)
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
		self.return_status = derive_return_status(self)
		self.status = derive_status(self)

	# ----------------------------------------------------------------- rules

	def run_rules(self, at_submit: bool = False):
		from gate_pass_management.gate_pass_management.doctype.gate_pass import validations

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
			from gate_pass_management.targets.cancel import cascade_cancel

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

		from gate_pass_management.targets.create import create_target

		# Deliberately NOT wrapped in a try/except that continues. A gate pass
		# configured to create its receipt automatically has not done its job if
		# the receipt is missing, and reporting success in that state is how the
		# implementations this app replaces produced phantom receipts.
		create_target(self.name, config.target_doctype, raise_on_error=True)

	# --------------------------------------------------------------- helpers

	def _log(self, event: str, **kwargs):
		from gate_pass_management.gate_pass_management.doctype.gate_pass_event_log.api import log_event

		log_event(gate_pass=self.name, event=event, **kwargs)

	def set_indicator(self):
		pass


# ===========================================================================
# Shared computations — one definition, so the three call sites cannot drift.
# ===========================================================================


def allowed_party_types() -> list[str]:
	"""The party types Gate Pass Settings permits, in the order it lists them."""
	return [r.party_type for r in guards.get_settings().get("allowed_party_types") or [] if r.party_type]


def series_for_direction(direction: str | None) -> str | None:
	"""The naming series Gate Pass Settings assigns to this direction.

	None when the site keeps one series for both directions, in which case the
	operator's own choice stands.
	"""
	if direction not in ("In", "Out"):
		return None
	settings = guards.get_settings()
	if not cint(settings.separate_series_by_direction):
		return None
	return (settings.naming_series_in if direction == "In" else settings.naming_series_out) or None


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

	return {
		"Returned": "Returned",
		"Partially Returned": "Partially Returned",
		"Overdue": "Overdue Return",
	}.get(derive_return_status(doc), "Pending Return")


def derive_return_status(doc) -> str:
	"""How much of a returnable outward pass has come back.

	Kept separate from `derive_status` because the two answer different
	questions — this one is only about the return leg, and it is what the
	Pending Returnable report and the overdue scheduler read.
	"""
	if doc.direction != "Out" or not doc.is_returnable:
		return "Not Applicable"

	returned = flt(doc.returned_qty)
	total = flt(doc.total_qty)

	if total and returned >= total:
		return "Returned"
	if returned > 0:
		return "Partially Returned"
	if doc.expected_return_date and getdate(doc.expected_return_date) < getdate(today()):
		return "Overdue"
	return "Pending"
