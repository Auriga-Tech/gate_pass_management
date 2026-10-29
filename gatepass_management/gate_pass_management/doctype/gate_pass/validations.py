"""Every Gate Pass validation, routed through the rule engine.

Each check calls `ctx.check(RULE_CODE, violated, message)`. The engine decides
whether that blocks, warns, or is skipped — this module never calls
`frappe.throw` directly, which is what makes per-rule enforcement possible
without touching fifty call sites.

Checks are grouped by when they run:

  * always      — every save
  * at submit   — expensive or final checks (ledger under lock, compliance)

Rules are collected rather than raised one at a time, so an operator sees
everything wrong with the pass in one message instead of discovering problems
one reload at a time with a truck waiting at the gate.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	cint,
	flt,
	get_datetime,
	get_link_to_form,
	getdate,
	now_datetime,
	time_diff_in_seconds,
	today,
)

from gatepass_management import ledger
from gatepass_management.compliance.base import PROVIDER_UNAVAILABLE
from gatepass_management.utils import guards


def run(doc, ctx, at_submit: bool = False):
	_document(doc, ctx)
	_party_and_source(doc, ctx)
	_items(doc, ctx)
	_discrepancy(doc, ctx)
	_weight_variance(doc, ctx)
	_mixed_grouping(doc, ctx)
	_field_rules(doc, ctx)

	if at_submit:
		_required_fields(doc, ctx)
		_ledger_under_lock(doc, ctx)
		_checklist(doc, ctx)
		_charges(doc, ctx)
		_inspection(doc, ctx)
		_compliance(doc, ctx)


# ---------------------------------------------------------------- document


def _document(doc, ctx):
	settings = guards.get_settings()

	if not doc.is_new():
		before = doc.get_doc_before_save()
		if before:
			ctx.check(
				"DOC-DIRECTION-LOCK",
				before.direction != doc.direction,
				_("Direction cannot be changed after the Gate Pass is saved. Create a new one instead."),
				fieldname="direction",
			)
			ctx.check(
				"DOC-DIRECTION-LOCK",
				before.gate_pass_type != doc.gate_pass_type,
				_("Type cannot be changed after the Gate Pass is saved."),
				fieldname="gate_pass_type",
			)

	ctx.check(
		"DOC-REF-DATE-FUTURE",
		bool(doc.reference_date) and getdate(doc.reference_date) > getdate(today()),
		_("Invoice / Challan Date cannot be in the future."),
		fieldname="reference_date",
	)

	if doc.posting_date:
		limit_days = int(ctx.threshold("DOC-BACKDATE", 7))
		if settings.allow_backdated and limit_days:
			ctx.check(
				"DOC-BACKDATE",
				getdate(doc.posting_date) < getdate(add_days(today(), -limit_days)),
				_("Gate Pass is dated more than {0} days ago.").format(limit_days),
				fieldname="posting_date",
			)
		elif not settings.allow_backdated:
			ctx.check(
				"DOC-BACKDATE",
				getdate(doc.posting_date) < getdate(today()),
				_("Backdated Gate Passes are not permitted."),
				fieldname="posting_date",
			)

		# `allow_future_dated` off means no future date at all, whatever the window says.
		future_days = int(ctx.threshold("DOC-FUTUREDATE", 0)) if settings.allow_future_dated else 0
		ctx.check(
			"DOC-FUTUREDATE",
			getdate(doc.posting_date) > getdate(add_days(today(), future_days)),
			_("Gate Pass cannot be dated in the future."),
			fieldname="posting_date",
		)

		if settings.enforce_from_date:
			ctx.check(
				"DOC-EFFECTIVE-DATE",
				doc.is_new() and getdate(doc.posting_date) < getdate(settings.enforce_from_date),
				_("Gate Pass is effective from {0}.").format(
					frappe.format_value(settings.enforce_from_date, {"fieldtype": "Date"})
				),
				fieldname="posting_date",
			)

	ctx.check(
		"DOC-RETURNABLE-DIR",
		bool(doc.is_returnable) and doc.direction == "In",
		_("Only outward Gate Passes can be marked returnable."),
		fieldname="is_returnable",
	)

	if doc.is_returnable and doc.expected_return_date and doc.posting_date:
		ctx.check(
			"DOC-RETURN-DATE",
			getdate(doc.expected_return_date) < getdate(doc.posting_date),
			_("Expected Return date cannot be before the Gate Pass date."),
			fieldname="expected_return_date",
		)
		window = int(ctx.threshold("DOC-RETURN-WINDOW", 90))
		if window:
			ctx.check(
				"DOC-RETURN-WINDOW",
				getdate(doc.expected_return_date) > getdate(add_days(doc.posting_date, window)),
				_("Expected Return is more than {0} days away.").format(window),
				fieldname="expected_return_date",
			)

	needs_items = doc.gate_pass_type not in ("Visitor", "Vehicle Only") and not (
		settings.allow_gate_pass_without_items
	)
	ctx.check(
		"DOC-ITEMS-REQUIRED",
		needs_items and not doc.items,
		_("Add at least one item."),
		fieldname="items",
	)

	if doc.tracking_id and settings.tracking_id_unique:
		clash = frappe.db.exists(
			"Gate Pass",
			{"tracking_id": doc.tracking_id, "docstatus": 1, "name": ["!=", doc.name or ""]},
		)
		ctx.check(
			"DOC-TRACKING-UNIQUE",
			bool(clash),
			_("Tracking ID {0} is already used on {1}.").format(
				frappe.bold(doc.tracking_id),
				get_link_to_form("Gate Pass", clash) if clash else "",
			),
			fieldname="tracking_id",
		)

	if doc.gate and doc.location:
		gate_location = frappe.db.get_value("Gate", doc.gate, "location")
		ctx.check(
			"DOC-GATE-LOCATION",
			bool(gate_location) and gate_location != doc.location,
			_("Gate {0} belongs to {1}, not {2}.").format(doc.gate, gate_location, doc.location),
			fieldname="gate",
		)

	ctx.check(
		"DOC-SECURITY-OFFICER",
		not doc.security_officer,
		_("No Security Officer is recorded on this Gate Pass."),
		fieldname="security_officer",
		remediation=_("Link your user to an Employee record so this fills automatically."),
	)

	if doc.company and doc.source_doctype and doc.source_document:
		source_company = frappe.db.get_value(doc.source_doctype, doc.source_document, "company")
		ctx.check(
			"DOC-COMPANY-MATCH",
			bool(source_company) and source_company != doc.company,
			_("Gate Pass company {0} does not match {1} on {2} {3}.").format(
				doc.company, source_company, _(doc.source_doctype), doc.source_document
			),
			fieldname="company",
		)


# -------------------------------------------------------- party and source


def _party_and_source(doc, ctx):
	config = ctx.source_config

	if doc.party_type and doc.party_type not in ("Contact", "Employee"):
		ctx.check(
			"PARTY-ADDRESS",
			not doc.address,
			_("Address is required for party type {0}.").format(doc.party_type),
			fieldname="address",
		)

	doctypes = {r.source_doctype for r in doc.items if r.source_doctype}
	ctx.check(
		"SRC-MIXED-DOCTYPE",
		len(doctypes) > 1,
		_("All item rows must come from the same document type. Found: {0}.").format(
			", ".join(sorted(doctypes))
		),
		fieldname="items",
	)

	documents = {r.source_document for r in doc.items if r.source_document}
	if not documents:
		return

	if doc.source_doctype:
		for name in sorted(documents):
			docstatus = frappe.db.get_value(doc.source_doctype, name, "docstatus")
			ctx.check(
				"SRC-SUBMITTED",
				docstatus != 1,
				_("{0} {1} must be submitted before a Gate Pass can be created against it.").format(
					_(doc.source_doctype), name
				),
			)

		if config and config.allowed_statuses:
			allowed = [s.strip() for s in config.allowed_statuses.split(",") if s.strip()]
			if allowed and frappe.get_meta(doc.source_doctype).has_field("status"):
				for name in sorted(documents):
					status = frappe.db.get_value(doc.source_doctype, name, "status")
					ctx.check(
						"SRC-STATUS",
						status not in allowed,
						_('{0} {1} has status "{2}" and is not open for a Gate Pass. Allowed: {3}.').format(
							_(doc.source_doctype), name, status, ", ".join(allowed)
						),
					)

	if len(documents) > 1 and doc.source_doctype and doc.party_type:
		party_field = frappe.scrub(doc.party_type)
		if frappe.get_meta(doc.source_doctype).has_field(party_field):
			parties = {
				frappe.db.get_value(doc.source_doctype, n, party_field) for n in documents
			}
			ctx.check(
				"SRC-MIXED-PARTY",
				len(parties) > 1,
				_("All rows must belong to documents of the same {0}. Found: {1}.").format(
					doc.party_type, ", ".join(sorted(str(p) for p in parties if p))
				),
			)

	if doc.party and doc.party_type and doc.source_doctype and len(documents) == 1:
		party_field = frappe.scrub(doc.party_type)
		if frappe.get_meta(doc.source_doctype).has_field(party_field):
			source_party = frappe.db.get_value(
				doc.source_doctype, next(iter(documents)), party_field
			)
			ctx.check(
				"PARTY-SOURCE-MATCH",
				bool(source_party) and source_party != doc.party,
				_("Gate Pass party {0} does not match {1} on {2}.").format(
					doc.party, source_party, next(iter(documents))
				),
				fieldname="party",
			)

	if config:
		ctx.check(
			"SRC-NONSTOCK-MIX",
			any(r.is_non_stock for r in doc.items),
			_("This Gate Pass was created from {0}; free-text items were added to it.").format(
				_(config.source_doctype)
			),
			fieldname="items",
		)


# ------------------------------------------------------------------ items


def _items(doc, ctx):
	config = ctx.source_config
	allow_zero = bool(config and config.allow_zero_qty_rows)
	tolerance = flt(ctx.threshold("QTY-ROW-PENDING", 0))
	allow_over = bool(config and config.allow_over_qty)
	if config and config.over_qty_allowance_pct:
		tolerance = flt(config.over_qty_allowance_pct)
	elif not tolerance:
		tolerance = flt(
			frappe.db.get_single_value("Stock Settings", "over_delivery_receipt_allowance") or 0
		)

	seen_rows: dict[str, int] = {}

	for row in doc.items:
		idx = row.idx

		ctx.check("QTY-NEGATIVE", flt(row.qty) < 0,
		          _("Qty cannot be negative."), row_idx=idx, fieldname="qty")

		if not allow_zero:
			ctx.check("QTY-ZERO", flt(row.qty) == 0,
			          _("Qty must be greater than zero."), row_idx=idx, fieldname="qty")

		ctx.check("ITEM-REQUIRED", not row.item_code and not row.is_non_stock,
		          _("Item is required. Tick 'Free Text Item' for goods with no Item master."),
		          row_idx=idx, fieldname="item_code")

		ctx.check("SRC-NONSTOCK-MIX",
		          bool(row.is_non_stock) and not settings_allows_non_stock(ctx),
		          _("Free-text items are disabled in Gate Pass Settings."),
		          row_idx=idx, fieldname="is_non_stock")

		ctx.check("ITEM-NAME-REQUIRED", bool(row.is_non_stock) and not row.item_name,
		          _("Item Name is required for free-text items."),
		          row_idx=idx, fieldname="item_name")

		ctx.check("ITEM-CONVERSION", flt(row.conversion_factor) <= 0,
		          _("Conversion Factor must be greater than zero."),
		          row_idx=idx, fieldname="conversion_factor")

		if row.source_row:
			if row.source_row in seen_rows:
				ctx.check(
					"QTY-DUPLICATE-ROW", True,
					_("This row and row {0} both reference the same source line. Merge them.").format(
						seen_rows[row.source_row]
					),
					row_idx=idx,
				)
			else:
				seen_rows[row.source_row] = idx

			if not allow_over and flt(row.pending_qty):
				maximum = flt(row.pending_qty) * (1 + tolerance / 100.0)
				ctx.check(
					"QTY-ROW-PENDING",
					flt(row.qty, 6) > flt(maximum, 6),
					_("Qty {0} exceeds the pending qty {1} on {2} (maximum {3} with {4}% allowance).").format(
						flt(row.qty), flt(row.pending_qty), row.source_document,
						flt(maximum, 3), tolerance,
					),
					row_idx=idx, fieldname="qty",
					values={"qty": flt(row.qty), "pending": flt(row.pending_qty)},
				)

		if config and config.qty_policy == "Editable within Tolerance" and flt(row.source_qty):
			variance = abs(flt(row.qty) - flt(row.source_qty)) / flt(row.source_qty) * 100
			limit = flt(ctx.threshold("QTY-POLICY-TOLERANCE", 5))
			ctx.check(
				"QTY-POLICY-TOLERANCE",
				variance > limit,
				_("Qty {0} differs from {1} on the source by {2}%, more than the permitted {3}%.").format(
					flt(row.qty), flt(row.source_qty), flt(variance, 1), limit
				),
				row_idx=idx, fieldname="qty",
			)

		if row.item_code and ctx.is_active("CHK-BATCH-SERIAL"):
			item = frappe.get_cached_value(
				"Item", row.item_code, ["has_batch_no", "has_serial_no"], as_dict=True
			)
			if item:
				ctx.check("CHK-BATCH-SERIAL",
				          bool(item.has_batch_no) and not row.batch_no,
				          _("Batch is required for item {0}.").format(row.item_code),
				          row_idx=idx, fieldname="batch_no")
				ctx.check("CHK-BATCH-SERIAL",
				          bool(item.has_serial_no) and not row.serial_no,
				          _("Serial numbers are required for item {0}.").format(row.item_code),
				          row_idx=idx, fieldname="serial_no")

	if ctx.is_active("QTY-WEIGHT") and (doc.gross_weight or doc.tare_weight):
		ctx.check("QTY-WEIGHT", flt(doc.net_weight) <= 0,
		          _("Net Weight must be greater than zero. Gross {0}, Tare {1}.").format(
			          flt(doc.gross_weight), flt(doc.tare_weight)),
		          fieldname="net_weight")


# ------------------------------------------------------------ discrepancy


def settings_allows_non_stock(ctx) -> bool:
	return bool(guards.get_settings().allow_non_stock_items)


def _discrepancy(doc, ctx):
	config = ctx.source_config
	allowed = bool(config.allow_discrepancy) if config else True

	for row in doc.items:
		idx = row.idx
		parts = flt(row.shortage_qty) + flt(row.damaged_qty) + flt(row.rejected_qty)

		ctx.check("DISC-NEGATIVE",
		          min(flt(row.shortage_qty), flt(row.damaged_qty), flt(row.rejected_qty)) < 0,
		          _("Discrepancy quantities cannot be negative."), row_idx=idx)

		if parts:
			ctx.check("DISC-ALLOWED", not allowed,
			          _("Discrepancies cannot be recorded on Gate Passes created from {0}.").format(
				          _(config.source_doctype) if config else ""),
			          row_idx=idx)

			ctx.check("DISC-REASON", not row.discrepancy_reason,
			          _("Select a Discrepancy Reason."), row_idx=idx,
			          fieldname="discrepancy_reason")

			ctx.check("DISC-REJ-WAREHOUSE",
			          flt(row.damaged_qty) > 0 and not row.rejected_warehouse
			          and bool(config and config.target_doctype),
			          _("Set a Rejected Warehouse so damaged qty can be received separately."),
			          row_idx=idx, fieldname="rejected_warehouse")

		total = flt(row.accepted_qty) + parts
		ctx.check(
			"DISC-BALANCE",
			flt(total, 6) != flt(row.qty, 6),
			_("Accepted {0} + Shortage {1} + Damaged {2} + Rejected {3} must equal Qty {4}.").format(
				flt(row.accepted_qty), flt(row.shortage_qty), flt(row.damaged_qty),
				flt(row.rejected_qty), flt(row.qty),
			),
			row_idx=idx, fieldname="accepted_qty",
		)

	if doc.has_discrepancy:
		ctx.check("DISC-NOTES", not (doc.discrepancy_notes or "").strip(),
		          _("Describe what happened in the Discrepancy section."),
		          fieldname="discrepancy_notes")

		limit = flt(ctx.threshold("DISC-THRESHOLD", 10))
		if limit and flt(doc.total_qty):
			affected = (
				flt(doc.total_shortage_qty) + flt(doc.total_damaged_qty) + flt(doc.total_rejected_qty)
			)
			pct = affected / flt(doc.total_qty) * 100
			ctx.check("DISC-THRESHOLD", pct > limit,
			          _("{0}% of this consignment is short, damaged or rejected.").format(flt(pct, 1)),
			          values={"pct": flt(pct, 2)})


# ------------------------------------------------------------- field rules


def _field_rules(doc, ctx):
	"""Customer-defined mandatory fields.

	Also enforced in the form script, but re-checked here because a rule that
	exists only in the browser is not a rule — API calls and data imports would
	sail past it.
	"""
	settings = guards.get_settings()
	for rule in settings.get("field_rules") or []:
		if not rule.is_mandatory:
			continue
		if rule.applies_to_direction not in ("Both", None, "", doc.direction):
			continue
		if rule.applies_to_gate_pass_type and rule.applies_to_gate_pass_type != doc.gate_pass_type:
			continue
		if rule.applies_to_source_type and rule.applies_to_source_type != doc.source_type:
			continue

		label = rule.custom_label or frappe.unscrub(rule.fieldname)
		action = rule.action or "Warn"

		if rule.document == "Gate Pass":
			empty = not doc.get(rule.fieldname)
			_field_rule_check(ctx, action, empty, label, fieldname=rule.fieldname)
		else:
			for row in doc.items:
				_field_rule_check(
					ctx, action, not row.get(rule.fieldname), label,
					fieldname=rule.fieldname, row_idx=row.idx,
				)


def _field_rule_check(ctx, action, violated, label, **kw):
	if not violated or action == "Ignore":
		return
	message = _("{0} is required.").format(frappe.bold(label))
	violation_list = ctx.violations if action == "Block" else ctx.warnings
	from gatepass_management.rules.engine import Violation

	violation_list.append(
		Violation(code="FIELD-RULE", action=action, message=message,
		          row_idx=kw.get("row_idx"), fieldname=kw.get("fieldname"))
	)


# -------------------------------------------------- submit-time validations


def _ledger_under_lock(doc, ctx):
	"""The definitive over-quantity check.

	Reads consumed quantity under a row lock on the source documents. A second
	operator submitting against the same order line at the same moment blocks
	here until the first commits, then sees the true total and fails properly —
	rather than both reading zero and both succeeding.
	"""
	if not ctx.is_active("QTY-LEDGER"):
		return

	rows = [r for r in doc.items if r.source_row]
	if not rows or not doc.source_doctype:
		return

	config = ctx.source_config
	if config and config.allow_over_qty:
		return

	tolerance = flt(config.over_qty_allowance_pct) if config and config.over_qty_allowance_pct else flt(
		ctx.threshold("QTY-LEDGER", 0)
	)
	if not tolerance:
		tolerance = flt(
			frappe.db.get_single_value("Stock Settings", "over_delivery_receipt_allowance") or 0
		)

	consumed = ledger.consumed_qty_for_update(
		source_doctype=doc.source_doctype,
		source_documents=list({r.source_document for r in rows if r.source_document}),
		source_rows=[r.source_row for r in rows],
		exclude_gate_pass=doc.name,
	)

	for row in rows:
		already = flt(consumed.get(row.source_row, 0))
		ordered = flt(row.source_qty)
		if not ordered:
			continue
		total = already + flt(row.qty)
		maximum = ordered * (1 + tolerance / 100.0)

		ctx.check(
			"QTY-LEDGER",
			flt(total, 6) > flt(maximum, 6),
			_(
				"Item {0}: total gate-passed qty {1} against this line exceeds the ordered qty {2} "
				"plus {3}% allowance (maximum {4}). Already passed on other Gate Passes: {5}."
			).format(
				row.item_code, flt(total, 3), ordered, tolerance, flt(maximum, 3), flt(already, 3)
			),
			row_idx=row.idx, fieldname="qty",
			values={"total": flt(total, 3), "ordered": ordered, "already": flt(already, 3)},
		)


def _checklist(doc, ctx):
	for row in doc.documents:
		if not row.is_mandatory or row.attachment:
			continue
		ctx.check(
			"CHK-DOC-MANDATORY", True,
			_("Attach the required document: {0}.").format(frappe.bold(row.document_name)),
			fieldname="documents",
		)


def _charges(doc, ctx):
	for row in doc.charges:
		if row.is_mandatory and not flt(row.amount):
			ctx.check("CHK-CHARGE-MANDATORY", True,
			          _("Enter an amount for {0}.").format(frappe.bold(row.charge_type)),
			          fieldname="charges")


# Gate Pass Settings → Required Fields. Checked at submit rather than on save,
# so a draft auto-created from a Purchase Order can exist before the vehicle
# arrives and the operator has anything to type into these.
_REQUIRED_BY_SETTING = {
	"require_location": ("location", "Location"),
	"require_gate": ("gate", "Gate"),
	"require_vehicle": ("vehicle_number", "Vehicle Number"),
	"require_driver": ("driver_name", "Driver Name"),
	"require_reference_no": ("reference_no", "Invoice / Challan No"),
}


def _required_fields(doc, ctx):
	"""Enforce the Required Fields switches in Gate Pass Settings.

	These shipped in Settings and were described in the User Manual but nothing
	read them, so ticking Vehicle Number as required had no effect at all.
	"""
	settings = guards.get_settings()
	for setting, (fieldname, label) in _REQUIRED_BY_SETTING.items():
		if not settings.get(setting):
			continue
		value = doc.get(fieldname)
		if isinstance(value, str):
			value = value.strip()
		if not value:
			_field_rule_check(ctx, "Block", True, _(label), fieldname=fieldname)


def _inspection(doc, ctx):
	settings = guards.get_settings()
	if settings.require_packaging_check:
		ctx.check("CHK-PACKAGING", not doc.packaging_condition,
		          _("Record the Packaging Condition."), fieldname="packaging_condition")
	if settings.require_documentation_check:
		ctx.check("CHK-DOCUMENTATION", not doc.documentation_status,
		          _("Record the Documentation status."), fieldname="documentation_status")
	if settings.require_vehicle_photo:
		ctx.check("CHK-VEHICLE-PHOTO", not doc.vehicle_photo,
		          _("Attach a vehicle photo."), fieldname="vehicle_photo")


def _compliance(doc, ctx):
	"""Re-evaluate statutory checks inside the submitting transaction.

	Not a repeat of the on-load check for its own sake: an IRN can be cancelled
	between the operator opening the form and pressing submit, and the whole
	point of gating at the gate is that the check reflects the moment the
	vehicle actually leaves.
	"""
	settings = guards.get_settings()
	if not settings.enable_compliance_checks:
		return

	from gatepass_management.compliance import runner

	config = ctx.source_config
	if not config or not config.get("compliance_rules"):
		return

	# CMP-STALE: a check evaluated long before submit may no longer be true. The
	# re-evaluation below is what keeps it honest, so the rule only has to decide
	# whether a stale reading is worth complaining about on its own.
	_compliance_staleness(doc, ctx, settings)

	results = runner.evaluate(doc, config)
	runner.sync_to_gate_pass(doc, results)

	by_code = {r.check_code: r for r in results}

	for rule in config.get("compliance_rules") or []:
		result = by_code.get(rule.check_code)
		if not result or result.passed:
			continue

		unreachable = result.status == PROVIDER_UNAVAILABLE
		code = "CMP-PROVIDER-DOWN" if unreachable else "CMP-REQUIRED"

		# `block_on_provider_failure` off means an unverifiable check is a warning
		# rather than a wall. It ships on: failing open is not a control.
		if unreachable and not cint(settings.block_on_provider_failure):
			ctx.warnings.append(
				_violation(code, "Warn", _("{0}: {1}").format(
					frappe.bold(result.label), result.message), result.remediation))
			continue

		# The compliance rule row carries its own action, which takes precedence
		# over the global rule. A site can block on E-Way Bill while warning on
		# E-Invoice without touching anything else.
		if rule.action == "Ignore":
			continue

		violated_message = _("{0}: {1}").format(frappe.bold(result.label), result.message)

		if rule.action == "Warn" and not _has_bypass(rule):
			ctx.warnings.append(_violation(code, "Warn", violated_message, result.remediation))
			continue

		if _has_bypass(rule):
			ctx.warnings.append(_violation(code, "Warn", violated_message, result.remediation))
			continue

		ctx.violations.append(_violation(code, "Block", violated_message, result.remediation))


def _has_bypass(rule) -> bool:
	roles = {r.role for r in (rule.get("bypass_roles") or []) if r.get("role")}
	return bool(roles & set(frappe.get_roles()))


def _violation(code, action, message, remediation=""):
	from gatepass_management.rules.engine import Violation

	return Violation(code=code, action=action, message=message, remediation=remediation)


def _compliance_staleness(doc, ctx, settings):
	"""Warn when the compliance reading on screen is older than the configured window.

	The check is re-run at submit regardless, so this never gates the pass. It
	exists so an operator who has had the form open for an hour is told the
	green ticks they are looking at were not current.
	"""
	minutes = cint(ctx.threshold("CMP-STALE", 10))
	if not minutes or not doc.compliance_checked_on:
		return

	age = time_diff_in_seconds(now_datetime(), get_datetime(doc.compliance_checked_on)) / 60
	ctx.check(
		"CMP-STALE",
		age > minutes,
		_("Compliance was last checked {0} minutes ago; it is being re-checked now.").format(
			cint(age)
		),
		fieldname="compliance_status",
	)


def _weight_variance(doc, ctx):
	"""Net weight against what the items say they should weigh.

	Only possible when every item carries a weight on the Item master; a single
	blank makes the expected total meaningless, so the check stands down rather
	than inventing a number.
	"""
	if not guards.get_settings().enable_weighbridge or not flt(doc.net_weight):
		return
	if not ctx.is_active("QTY-WEIGHT-VARIANCE"):
		return

	expected = 0.0
	for row in doc.items:
		if not row.item_code:
			return
		per_unit = flt(frappe.get_cached_value("Item", row.item_code, "weight_per_unit"))
		if not per_unit:
			return
		expected += per_unit * flt(row.stock_qty or row.qty)

	if not expected:
		return

	variance = abs(flt(doc.net_weight) - expected) / expected * 100
	limit = flt(ctx.threshold("QTY-WEIGHT-VARIANCE", 10))
	ctx.check(
		"QTY-WEIGHT-VARIANCE",
		variance > limit,
		_("Net weight {0} differs from the expected {1} by {2}%, more than the permitted {3}%.").format(
			flt(doc.net_weight, 3), flt(expected, 3), flt(variance, 1), limit
		),
		fieldname="net_weight",
		values={"net_weight": flt(doc.net_weight), "expected": flt(expected, 3)},
	)


def _mixed_grouping(doc, ctx):
	"""Multi-source passes should not mix documents that differ on key fields.

	Which fields matter varies by install — one site cares that every purchase
	order on a pass shares a purchase type, another does not care at all — so the
	list comes from Gate Pass Settings and the check stands down when it is empty.
	"""
	documents = {r.source_document for r in doc.items if r.source_document}
	if len(documents) < 2 or not doc.source_doctype:
		return
	if not ctx.is_active("SRC-MIXED-GROUP"):
		return

	raw = (guards.get_settings().get("group_by_fields") or "").strip()
	if not raw:
		return

	meta = frappe.get_meta(doc.source_doctype)
	for fieldname in [f.strip() for f in raw.replace("\n", ",").split(",") if f.strip()]:
		if not meta.has_field(fieldname):
			continue
		values = {
			frappe.db.get_value(doc.source_doctype, name, fieldname) for name in sorted(documents)
		}
		values.discard(None)
		ctx.check(
			"SRC-MIXED-GROUP",
			len(values) > 1,
			_("The {0}s on this Gate Pass have different {1}: {2}.").format(
				_(doc.source_doctype),
				frappe.bold(meta.get_label(fieldname)),
				", ".join(sorted(str(v) for v in values)),
			),
			fieldname="items",
		)
