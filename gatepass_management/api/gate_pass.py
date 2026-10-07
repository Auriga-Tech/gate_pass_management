"""Public API.

Every method here checks permissions explicitly, returns structured data, and
never commits mid-request. The post-submit mutations (timestamps, discrepancy,
compliance override) are the operations most worth tampering with, so each one
is role-gated, requires a reason, and writes an audit event.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, get_link_to_form, now_datetime, today

from gatepass_management import ledger
from gatepass_management.gate_pass.doctype.gate_pass_event_log.api import log_event
from gatepass_management.utils import guards
from gatepass_management.utils.logger import get_logger


# ---------------------------------------------------------------- sources


@frappe.whitelist()
def list_sources(direction: str | None = None, source_doctype: str | None = None) -> list[dict]:
	"""Flows available to this user — drives the 'Get Items From' button group."""
	filters = {"enabled": 1}
	if direction:
		filters["direction"] = direction
	if source_doctype:
		filters["source_doctype"] = source_doctype

	roles = set(frappe.get_roles())
	out = []

	for source in frappe.get_all(
		"Gate Pass Source",
		filters=filters,
		fields=["name", "button_label", "direction", "source_doctype", "sub_type",
		        "sequence", "allow_row_selection", "row_columns", "dialog_fields",
		        "source_filters", "party_type", "qty_policy", "description"],
		order_by="sequence asc, source_name asc",
	):
		allowed = {
			r.role
			for r in frappe.get_all(
				"Gate Pass Role",
				filters={"parent": source.name, "parentfield": "allowed_roles"},
				fields=["role"],
			)
		}
		if allowed and not (allowed & roles):
			continue
		out.append(source)

	return out


@frappe.whitelist()
def get_pending(source_doctype: str, source_name: str, source_type: str) -> dict:
	"""Pending quantity per source row. Display only — see ledger.py."""
	_check_source_access(source_doctype, source_name)
	config = frappe.get_cached_doc("Gate Pass Source", source_type)
	return ledger.pending_qty(source_doctype, source_name, config)


@frappe.whitelist()
def build_gate_pass(source_type: str, source_name: str, target_doc=None, rows=None):
	"""The single generic mapper.

	One function for every flow. The eight near-identical mapper functions in the
	implementations this app replaces are now twelve rows of configuration.

	`source_name` is one document name or a JSON list of them: the picker allows
	several documents, and a gate pass may span them when they share a party.
	"""
	config = frappe.get_cached_doc("Gate Pass Source", source_type)

	names = _as_list(source_name)
	if not names:
		frappe.throw(_("Select at least one document."))

	if isinstance(rows, str):
		rows = json.loads(rows)
	selected = set(rows or [])

	gp = frappe.new_doc("Gate Pass") if not target_doc else frappe.get_doc(json.loads(target_doc))

	for name in names:
		_add_source(gp, config, name, selected)
	return gp


def _as_list(value) -> list[str]:
	if isinstance(value, str):
		value = value.strip()
		if value.startswith("["):
			value = json.loads(value)
		else:
			value = [value] if value else []
	seen, out = set(), []
	for v in value or []:
		if v and v not in seen:
			seen.add(v)
			out.append(v)
	return out


def _add_source(gp, config, source_name: str, selected: set):
	"""Append the pending rows of one source document to the gate pass."""
	_check_source_access(config.source_doctype, source_name)

	source_doc = frappe.get_doc(config.source_doctype, source_name)
	if source_doc.docstatus != 1:
		frappe.throw(
			_("{0} {1} must be submitted first.").format(_(config.source_doctype), source_name)
		)

	pending = ledger.pending_qty(config.source_doctype, source_name, config)
	if not pending or not any(v["pending"] > 0 for v in pending.values()):
		_throw_already_passed(config, source_name)

	from gatepass_management.sources.automation import _resolve_party

	party_type, party = _resolve_party(config, source_doc)
	if gp.items and gp.party and party and (gp.party_type, gp.party) != (party_type or gp.party_type, party):
		frappe.throw(
			_("{0} {1} belongs to {2}, but this Gate Pass is for {3}. One Gate Pass covers one party.").format(
				_(config.source_doctype), source_name, party, gp.party
			),
			title=_("Different party"),
		)

	first = not gp.items
	gp.company = source_doc.get("company") or gp.company
	gp.source_type = config.name
	gp.source_doctype = config.source_doctype
	gp.source_sub_type = config.sub_type
	gp.direction = config.direction
	if first or not gp.source_document:
		gp.source_document = source_name
		gp.source_document_date = source_doc.get("posting_date") or source_doc.get("transaction_date")
	gp.party_type = party_type or gp.party_type
	gp.party = party or gp.party

	child_doctype = frappe.get_meta(config.source_doctype).get_field(config.child_table).options
	child_rows = frappe.get_all(
		child_doctype,
		filters={"parent": source_name, "parenttype": config.source_doctype},
		fields=["*"],
		order_by="idx asc",
	)

	already_here = {r.source_row for r in gp.items if r.source_row}
	added = skipped = 0
	for row in child_rows:
		if selected and row.name not in selected:
			continue
		info = pending.get(row.name)
		if not info or info["pending"] <= 0:
			continue

		item_code = row.get(config.item_field)
		if item_code and frappe.db.get_value("Item", item_code, "exclude_from_gate_pass"):
			continue

		# Picking the same document twice must not double the quantities.
		if row.name in already_here:
			skipped += 1
			continue

		qty = info["pending"]
		gp.append(
			"items",
			{
				"item_code": item_code,
				# Some source rows (Subcontracting Order raw materials, a returning Gate Pass)
				# carry no item_name of their own, so take it from the Item master.
				"item_name": row.get("item_name")
				or (item_code and frappe.get_cached_value("Item", item_code, "item_name")),
				"uom": row.get(config.uom_field) if config.uom_field else None,
				"conversion_factor": row.get("conversion_factor") or 1,
				"source_qty": info["source_qty"],
				"already_passed_qty": info["consumed"],
				"pending_qty": qty,
				"qty": qty,
				"accepted_qty": qty,
				"rate": row.get(config.rate_field) if config.rate_field else None,
				"warehouse": row.get(config.warehouse_field) if config.warehouse_field else None,
				"bom": row.get(config.bom_field) if config.bom_field else None,
				"source_doctype": config.source_doctype,
				"source_document": source_name,
				"source_row": row.name,
			},
		)
		added += 1

	if not added:
		if skipped:
			frappe.throw(
				_("{0} {1} is already on this Gate Pass.").format(_(config.source_doctype), source_name),
				title=_("Already added"),
			)
		_throw_already_passed(config, source_name)

	_apply_header_map(config, source_doc, gp)


def _apply_header_map(config, source_doc, gp):
	for row in config.get("field_map") or []:
		if row.level != "Header":
			continue
		value = source_doc.get(row.source_field) or row.default_value
		if value and gp.meta.has_field(row.target_field):
			gp.set(row.target_field, value)


def _throw_already_passed(config, source_name):
	"""Explain, with links, rather than just refusing."""
	existing = frappe.get_all(
		"Gate Pass Item",
		filters={"source_document": source_name, "docstatus": 1},
		pluck="parent",
		distinct=True,
	)
	links = ", ".join(get_link_to_form("Gate Pass", n) for n in existing)
	frappe.throw(
		_("Everything on {0} {1} has already been gate passed.{2}").format(
			_(config.source_doctype), source_name,
			_("<br>Existing Gate Passes: {0}").format(links) if links else "",
		),
		title=_("Nothing left to pass"),
	)


# ---------------------------------------------------- post-submit changes


@frappe.whitelist()
def amend_timestamp(gate_pass: str, fieldname: str, value: str, reason: str):
	"""Correct an entry or exit time after submission.

	Operationally necessary — clocks are wrong, shifts change over, a pass gets
	submitted an hour late. But this is the field an auditor cares most about,
	so it is role-gated, requires a reason, and records the old value.
	"""
	if fieldname not in ("entry_datetime", "exit_datetime"):
		frappe.throw(_("Only entry and exit times can be amended."))
	if not (reason or "").strip():
		frappe.throw(_("A reason is required."))

	_require_role("timestamp_edit_roles", _("amend entry and exit times"))
	frappe.has_permission("Gate Pass", "write", gate_pass, throw=True)

	old = frappe.db.get_value("Gate Pass", gate_pass, fieldname)
	frappe.db.set_value("Gate Pass", gate_pass, fieldname, value, update_modified=False)
	frappe.db.set_value("Gate Pass", gate_pass, "timestamps_amended", 1, update_modified=False)

	log_event(
		gate_pass=gate_pass, event="Timestamp Amended",
		field_changed=fieldname, old_value=old, new_value=value, reason=reason,
		message=_("{0} changed from {1} to {2}").format(
			frappe.unscrub(fieldname), old or _("blank"), value
		),
	)
	get_logger().info(
		"timestamp_amended",
		extra={"gate_pass": gate_pass, "field": fieldname, "old": str(old), "new": value},
	)
	return {"ok": True}


@frappe.whitelist()
def record_discrepancy(gate_pass: str, rows: str, notes: str, reason: str = ""):
	"""Record shortage, damage or rejection after the pass was submitted.

	Damage is usually found while unloading, which happens after the vehicle is
	through the gate. Forcing a cancel-and-amend for that would push people to
	simply not record it — so it is allowed, audited, and refused once a target
	document exists.
	"""
	settings = guards.get_settings()
	if not settings.allow_post_submit_discrepancy:
		frappe.throw(_("Recording discrepancies after submission is disabled in Gate Pass Settings."))

	_require_role("post_submit_discrepancy_roles", _("record discrepancies after submission"))
	frappe.has_permission("Gate Pass", "write", gate_pass, throw=True)

	gp = frappe.get_doc("Gate Pass", gate_pass)
	if gp.docstatus != 1:
		frappe.throw(_("This Gate Pass is not submitted."))

	submitted_targets = [
		r for r in gp.references
		if r.link_type == "Target"
		and frappe.db.get_value(r.reference_doctype, r.reference_name, "docstatus") == 1
	]
	if submitted_targets:
		links = ", ".join(
			get_link_to_form(r.reference_doctype, r.reference_name) for r in submitted_targets
		)
		frappe.throw(
			_("Discrepancy cannot be changed after {0} has been submitted. Cancel it first.").format(
				links
			),
			title=_("Already processed"),
		)

	payload = json.loads(rows) if isinstance(rows, str) else rows
	changes = []

	for row in gp.items:
		update = payload.get(row.name)
		if not update:
			continue
		old = {
			"accepted": flt(row.accepted_qty), "shortage": flt(row.shortage_qty),
			"damaged": flt(row.damaged_qty), "rejected": flt(row.rejected_qty),
		}
		row.shortage_qty = flt(update.get("shortage_qty"))
		row.damaged_qty = flt(update.get("damaged_qty"))
		row.rejected_qty = flt(update.get("rejected_qty"))
		row.discrepancy_reason = update.get("discrepancy_reason") or row.discrepancy_reason
		row.rejected_warehouse = update.get("rejected_warehouse") or row.rejected_warehouse
		row.accepted_qty = (
			flt(row.qty) - row.shortage_qty - row.damaged_qty - row.rejected_qty
		)
		if row.accepted_qty < 0:
			frappe.throw(
				_("Row {0}: shortage, damage and rejection together exceed the qty {1}.").format(
					row.idx, flt(row.qty)
				)
			)
		changes.append((row.item_code, old, {
			"accepted": flt(row.accepted_qty), "shortage": flt(row.shortage_qty),
			"damaged": flt(row.damaged_qty), "rejected": flt(row.rejected_qty),
		}))

	gp.discrepancy_notes = notes
	gp.discrepancy_reported_by = frappe.session.user
	gp.discrepancy_reported_on = now_datetime()
	gp.flags.ignore_validate_update_after_submit = True
	gp.save(ignore_permissions=True)

	for item_code, old, new in changes:
		log_event(
			gate_pass=gate_pass, event="Discrepancy Recorded",
			message=_("{0}: accepted {1}, shortage {2}, damaged {3}, rejected {4}").format(
				item_code, new["accepted"], new["shortage"], new["damaged"], new["rejected"]
			),
			old_value=old, new_value=new, reason=reason or notes,
		)

	return {"ok": True, "rows_changed": len(changes)}


@frappe.whitelist()
def get_party_config() -> dict:
	"""Party types the form offers, and the one to preselect for a direction."""
	from gatepass_management.gate_pass.doctype.gate_pass.gate_pass import allowed_party_types

	allowed = allowed_party_types()
	default = guards.get_settings().default_party_type
	return {
		"allowed": allowed,
		"default": default if default in allowed else None,
		"allow_add_item_rows": bool(guards.get_settings().get("allow_add_item_rows")),
		# Material arriving is from a supplier; material leaving goes to a customer.
		"by_direction": {
			d: t for d, t in (("In", "Supplier"), ("Out", "Customer")) if t in allowed
		},
	}


@frappe.whitelist()
def get_party_defaults(party_type: str, party: str) -> dict:
	"""Default address, contact and mobile for the party chosen on a gate pass.

	Frappe exposes the default-address lookup but not the contact one, and a gate
	operator has no Customer or Supplier access to read them directly. Whoever may
	create a Gate Pass may fetch these three values for the party they pick.
	"""
	from frappe.contacts.doctype.address.address import get_default_address
	from frappe.contacts.doctype.contact.contact import get_default_contact

	from gatepass_management.gate_pass.doctype.gate_pass.gate_pass import allowed_party_types

	if party_type not in allowed_party_types():
		frappe.throw(_("Party Type must be one of: {0}.").format(", ".join(allowed_party_types())))
	if not frappe.has_permission(party_type, "read", party) and not frappe.has_permission(
		"Gate Pass", "create"
	):
		frappe.throw(_("You do not have permission to read {0} {1}.").format(_(party_type), party),
		             frappe.PermissionError)

	out = {"address": None, "contact_person": None, "contact_mobile": None}
	if not frappe.db.exists(party_type, party):
		return out

	out["address"] = get_default_address(party_type, party)
	contact = get_default_contact(party_type, party)
	if contact:
		out["contact_person"] = contact
		mobile, phone = frappe.db.get_value("Contact", contact, ["mobile_no", "phone"]) or (None, None)
		out["contact_mobile"] = mobile or phone
	return out


@frappe.whitelist()
def can_override_compliance() -> bool:
	"""Whether to show this user the Override button; override_compliance still enforces it."""
	return _has_role("compliance_override_roles")


@frappe.whitelist()
def override_compliance(gate_pass: str, reason: str):
	"""Record a deliberate decision to release without a statutory document.

	Deliberately never silent. Someone answers for this, and the Compliance
	Exceptions report is where an auditor finds them.
	"""
	if not (reason or "").strip():
		frappe.throw(_("A reason is required to override a compliance check."))

	_require_role("compliance_override_roles", _("override compliance checks"))
	frappe.has_permission("Gate Pass", "submit", gate_pass, throw=True)

	frappe.db.set_value("Gate Pass", gate_pass, {
		"compliance_override_by": frappe.session.user,
		"compliance_override_reason": reason,
	}, update_modified=False)

	log_event(
		gate_pass=gate_pass, event="Compliance Overridden",
		reason=reason,
		message=_("Compliance requirement overridden by {0}.").format(
			frappe.utils.get_fullname(frappe.session.user)
		),
	)
	get_logger().warning(
		"compliance_overridden",
		extra={"gate_pass": gate_pass, "user": frappe.session.user, "reason": reason},
	)
	return {"ok": True}


@frappe.whitelist()
def refresh_compliance(gate_pass: str) -> dict:
	"""Re-run compliance checks without losing entered data.

	The operator presses this after the sales team generates the missing
	document, while the vehicle waits.
	"""
	frappe.has_permission("Gate Pass", "read", gate_pass, throw=True)

	from gatepass_management.compliance import runner

	gp = frappe.get_doc("Gate Pass", gate_pass)
	config = frappe.get_cached_doc("Gate Pass Source", gp.source_type) if gp.source_type else None
	results = runner.evaluate(gp, config)

	return {
		"status": runner.roll_up(results),
		"checks": [
			{
				"label": r.label, "status": r.status, "document_no": r.document_no,
				"message": r.message, "remediation": r.remediation,
				"indicator": r.indicator, "detail_url": r.detail_url,
			}
			for r in results
		],
	}


# -------------------------------------------------------------- gate desk


@frappe.whitelist()
def scan(code: str) -> dict:
	"""Look up a gate pass from a QR or barcode scan."""
	code = (code or "").strip()
	if not code:
		frappe.throw(_("Nothing scanned."))

	name = code if frappe.db.exists("Gate Pass", code) else frappe.db.get_value(
		"Gate Pass", {"tracking_id": code}, "name"
	)
	if not name:
		frappe.throw(_("No Gate Pass found for {0}.").format(frappe.bold(code)))

	frappe.has_permission("Gate Pass", "read", name, throw=True)
	gp = frappe.get_doc("Gate Pass", name)
	return {
		"name": gp.name, "direction": gp.direction, "status": gp.status,
		"party": gp.party_name or gp.party, "vehicle_number": gp.vehicle_number,
		"driver_name": gp.driver_name, "total_qty": flt(gp.total_qty),
		"compliance_status": gp.compliance_status,
		"posting_date": gp.posting_date, "posting_time": gp.posting_time,
	}


@frappe.whitelist()
def yard_status(location: str | None = None) -> list[dict]:
	"""What is currently inside the premises."""
	filters = {"docstatus": 1, "status": ["in", ["Inside", "At Gate", "Partially Processed"]]}
	if location:
		filters["location"] = location
	return frappe.get_all(
		"Gate Pass",
		filters=filters,
		fields=["name", "direction", "status", "party", "vehicle_number",
		        "entry_datetime", "total_qty", "location"],
		order_by="entry_datetime asc",
		limit=200,
	)


# ------------------------------------------------------------------ misc


def _check_source_access(source_doctype: str, source_name: str):
	"""Who may read a source document to build a gate pass from it.

	A guard needs to pull items from a Purchase Order or Delivery Note without
	holding any Buying, Selling or Stock role, which they never should. Whoever
	may create a Gate Pass may therefore read the source for that purpose only;
	everyone else still needs ordinary read permission on the document.
	"""
	if frappe.has_permission(source_doctype, "read", source_name):
		return
	if frappe.has_permission("Gate Pass", "create"):
		return
	frappe.throw(
		_("You do not have permission to read {0} {1}.").format(_(source_doctype), source_name),
		frappe.PermissionError,
	)


def _has_role(settings_field: str) -> bool:
	settings = guards.get_settings()
	allowed = {r.role for r in settings.get(settings_field) or []}
	if not allowed:
		allowed = {"Gate Pass Manager"}
	roles = set(frappe.get_roles())
	return bool(allowed & roles) or "Administrator" in roles


def _require_role(settings_field: str, action: str):
	if _has_role(settings_field):
		return
	settings = guards.get_settings()
	allowed = {r.role for r in settings.get(settings_field) or []} or {"Gate Pass Manager"}
	frappe.throw(
		_("You do not have permission to {0}. Required role: {1}.").format(
			action, ", ".join(sorted(allowed))
		),
		frappe.PermissionError,
	)
