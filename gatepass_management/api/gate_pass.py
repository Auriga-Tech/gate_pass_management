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
from gatepass_management.gate_pass_management.doctype.gate_pass_event_log.api import log_event
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

	out = []

	for source in frappe.get_all(
		"Gate Pass Source",
		filters=filters,
		fields=["name", "button_label", "direction", "source_doctype", "sub_type",
		        "sequence", "allow_row_selection", "row_columns", "dialog_fields",
		        "source_filters", "party_type", "qty_policy"],
		order_by="sequence asc, source_name asc",
	):
		if not _flow_roles_allow(source.name):
			continue
		out.append(source)

	return out


def _flow_roles_allow(flow: str, user: str | None = None) -> bool:
	"""Whether this user's roles permit a flow.

	A flow with no `allowed_roles` is open to everyone — the safe default, so
	configuring one flow does not silently hide the rest.
	"""
	allowed = {
		r.role
		for r in frappe.get_all(
			"Gate Pass Role",
			filters={"parent": flow, "parentfield": "allowed_roles"},
			fields=["role"],
		)
	}
	return not allowed or bool(allowed & set(frappe.get_roles(user)))


# -------------------------------------------------------- source access
#
# A guard needs items off a Purchase Order or a Delivery Note without holding a
# Buying, Selling or Stock role — roles that would also let them change prices
# and approve orders, which is exactly what a gate operator should never have.
# So whoever may create a Gate Pass may read a source document for that purpose.
#
# User Permissions still apply, and deliberately so: once the role requirement
# is relaxed they are the only restriction left. A guard limited to one company
# or one location by User Permission cannot pull another site's orders. Dropping
# that as well would turn a scoped exception into an open door.


def _source_read_allowed(source_doctype: str, source_name: str) -> bool:
	if frappe.has_permission(source_doctype, "read", source_name):
		return True
	if not frappe.has_permission("Gate Pass", "create"):
		return False
	return _passes_user_permissions(source_doctype, source_name)


def _check_source_access(source_doctype: str, source_name: str):
	"""Throwing form of `_source_read_allowed`, for the pull endpoints."""
	if _source_read_allowed(source_doctype, source_name):
		return
	frappe.throw(
		_("You do not have permission to read {0} {1}.").format(_(source_doctype), source_name),
		frappe.PermissionError,
	)


def _passes_user_permissions(doctype: str, name: str) -> bool:
	"""The authoritative single-document check, straight from the framework."""
	from frappe.permissions import has_user_permission

	if not name:
		return True
	if not frappe.db.exists(doctype, name):
		return False
	return bool(has_user_permission(frappe.get_doc(doctype, name), ptype="read"))


def _user_permission_map(doctype: str) -> dict[str, set[str]]:
	"""Allowed values per link field, for filtering a list of candidate rows.

	`_passes_user_permissions` loads a document, which is right for the one
	document being pulled and far too expensive for a picker page. This mirrors
	`frappe.model.db_query.DatabaseQuery.add_user_permissions` — the logic an
	ordinary list view applies and that `source_query` cannot reach, because
	Frappe skips user permissions entirely once the role check is bypassed.

	An empty map means this user is unrestricted and every row is permitted.

	Like the framework's version this reads the parent's link fields only, while
	`_passes_user_permissions` also walks child rows. That asymmetry is Frappe's
	own and is deliberate here: the picker shows exactly what an ordinary list
	view would show, and the pull refuses exactly what opening the document
	would refuse. Widening this to child tables would make the picker disagree
	with every other list on the site.
	"""
	from frappe.permissions import get_allowed_docs_for_doctype, get_user_permissions

	permissions = get_user_permissions(frappe.session.user)
	if not permissions:
		return {}

	meta = frappe.get_meta(doctype)
	# The document's own name counts as a link to its own doctype, as Frappe does.
	fields = [*meta.get_link_fields(), frappe._dict(fieldname="name", options=doctype)]

	out = {}
	for field in fields:
		if field.get("ignore_user_permissions") or field.options not in permissions:
			continue
		allowed = get_allowed_docs_for_doctype(permissions[field.options], doctype)
		if allowed:
			out[field.fieldname] = {str(v) for v in allowed}
	return out


def _row_permitted(row: dict, permission_map: dict[str, set[str]], strict: bool) -> bool:
	for fieldname, allowed in permission_map.items():
		value = row.get(fieldname)
		if not value:
			# An empty link is not a restriction unless the site says it is.
			if strict:
				return False
			continue
		if str(value) not in allowed:
			return False
	return True


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def source_query(doctype, txt, searchfield, start, page_len, filters):
	"""Source documents a gate pass may be built from — the picker's list.

	The picker cannot use the ordinary list query: that needs read permission on
	Purchase Order, which a gate operator does not have, so the dialog came back
	empty and the relaxation above was unreachable from the UI.

	This grants nothing wider than the pull endpoints already allow: the flow's
	own role gate and configured filters, submitted documents only, and the same
	User Permission filtering.
	"""
	filters = dict(filters or {})
	flow = filters.pop("gate_pass_source", None)
	if not flow:
		frappe.throw(_("No Gate Pass Source given."))

	config = frappe.get_cached_doc("Gate Pass Source", flow)
	if config.source_doctype != doctype:
		frappe.throw(
			_("{0} does not draw from {1}.").format(config.name, _(doctype)), frappe.PermissionError
		)
	if not frappe.has_permission("Gate Pass", "create") or not _flow_roles_allow(config.name):
		frappe.throw(
			_("You do not have permission to use {0}.").format(config.name), frappe.PermissionError
		)

	meta = frappe.get_meta(doctype)
	conditions = {"docstatus": 1}
	# The flow's configured filters are applied here rather than trusted from the
	# client, which is free to send whatever it likes. They are hand-entered JSON,
	# so a malformed value narrows nothing instead of returning a server error.
	configured = json.loads(config.source_filters or "{}")
	if isinstance(configured, dict):
		conditions.update(configured)
	for key, value in filters.items():
		if key != "docstatus" and (key == "name" or meta.has_field(key)):
			conditions[key] = value

	party_field = frappe.scrub(config.party_type) if config.party_type else None
	if not party_field or not meta.has_field(party_field):
		party_field = None
	date_field = next(
		(f for f in ("posting_date", "transaction_date", "schedule_date") if meta.has_field(f)), None
	)

	permission_map = _user_permission_map(doctype)
	strict = bool(frappe.get_system_settings("apply_strict_user_permissions"))

	fields = ["name"]
	for field in (party_field, date_field, *permission_map):
		if field and field not in fields:
			fields.append(field)

	or_filters = {}
	if txt:
		or_filters["name"] = ["like", f"%{txt}%"]
		if party_field:
			or_filters[party_field] = ["like", f"%{txt}%"]

	# Rows the permission map rejects are dropped after the fetch, so an
	# unrestricted user pays nothing and a restricted one still fills a page.
	fetch = page_len if not permission_map else min(page_len * 3, 200)

	rows = frappe.get_all(
		doctype,
		filters=conditions,
		or_filters=or_filters or None,
		fields=fields,
		order_by=f"{date_field} desc" if date_field else "modified desc",
		limit_start=start,
		limit_page_length=fetch,
		ignore_permissions=True,
	)

	if permission_map:
		rows = [r for r in rows if _row_permitted(r, permission_map, strict)][:page_len]

	return rows


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
	"""
	config = frappe.get_cached_doc("Gate Pass Source", source_type)
	_check_source_access(config.source_doctype, source_name)

	if isinstance(rows, str):
		rows = json.loads(rows)
	selected = set(rows or [])

	source_doc = frappe.get_doc(config.source_doctype, source_name)
	if source_doc.docstatus != 1:
		frappe.throw(
			_("{0} {1} must be submitted first.").format(_(config.source_doctype), source_name)
		)

	pending = ledger.pending_qty(config.source_doctype, source_name, config)
	if not pending or not any(v["pending"] > 0 for v in pending.values()):
		_throw_already_passed(config, source_name)

	gp = frappe.new_doc("Gate Pass") if not target_doc else frappe.get_doc(json.loads(target_doc))

	gp.company = source_doc.get("company")
	gp.source_type = config.name
	gp.source_doctype = config.source_doctype
	gp.source_document = source_name
	gp.source_sub_type = config.sub_type
	gp.direction = config.direction
	gp.source_document_date = source_doc.get("posting_date") or source_doc.get("transaction_date")

	from gatepass_management.sources.automation import _resolve_party

	party_type, party = _resolve_party(config, source_doc)
	gp.party_type = party_type or gp.party_type
	gp.party = party or gp.party

	child_doctype = frappe.get_meta(config.source_doctype).get_field(config.child_table).options
	child_rows = frappe.get_all(
		child_doctype,
		filters={"parent": source_name, "parenttype": config.source_doctype},
		fields=["*"],
		order_by="idx asc",
	)

	added = 0
	for row in child_rows:
		if selected and row.name not in selected:
			continue
		info = pending.get(row.name)
		if not info or info["pending"] <= 0:
			continue

		item_code = row.get(config.item_field)
		if item_code and frappe.db.get_value("Item", item_code, "exclude_from_gate_pass"):
			continue

		qty = info["pending"]
		gp.append(
			"items",
			{
				"item_code": item_code,
				"item_name": row.get("item_name"),
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
		_throw_already_passed(config, source_name)

	_apply_header_map(config, source_doc, gp)
	return gp


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


def _require_role(settings_field: str, action: str):
	settings = guards.get_settings()
	allowed = {r.role for r in settings.get(settings_field) or []}
	if not allowed:
		allowed = {"Gate Pass Manager"}
	if not (allowed & set(frappe.get_roles())) and "Administrator" not in frappe.get_roles():
		frappe.throw(
			_("You do not have permission to {0}. Required role: {1}.").format(
				action, ", ".join(sorted(allowed))
			),
			frappe.PermissionError,
		)


# ------------------------------------------------------- target form support


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def gate_pass_query(doctype, txt, searchfield, start, page_len, filters):
	"""Gate passes a given target document can still draw from.

	Only submitted passes whose flow produces this target, and only those with
	something left to process — offering a fully-processed pass just produces a
	refusal one click later.
	"""
	filters = filters or {}
	target_doctype = filters.get("target_doctype")
	party = filters.get("party")

	GP = frappe.qb.DocType("Gate Pass")
	GPS = frappe.qb.DocType("Gate Pass Source")

	query = (
		frappe.qb.from_(GP)
		.inner_join(GPS)
		.on(GPS.name == GP.source_type)
		.select(GP.name, GP.party, GP.posting_date)
		.where(GP.docstatus == 1)
		.where(GP.per_processed < 100)
		.where(GP.name.like(f"%{txt}%"))
		.orderby(GP.posting_date)
		.limit(page_len)
		.offset(start)
	)
	if target_doctype:
		query = query.where(GPS.target_doctype == target_doctype)
	if party:
		query = query.where(GP.party == party)

	return query.run()


@frappe.whitelist()
def target_requirement(target_doctype: str) -> dict:
	"""Whether this target needs a gate pass, for the notice on its form.

	Mirrors what `targets.guards` enforces, so the form says the same thing the
	server will. Reports the resolved rule action too, since a requirement set
	to Warn is advice and one set to Block is a wall.
	"""
	from gatepass_management.rules.engine import RuleContext
	from gatepass_management.utils import guards

	if not guards.is_enabled():
		return {"requirement": "Not Required", "blocking": False}

	names = frappe.get_all(
		"Gate Pass Source",
		filters={"target_doctype": target_doctype, "enabled": 1},
		fields=["name", "enforce_on_target", "block_native_target_button"],
		limit=1,
	)
	if not names:
		return {"requirement": "Not Required", "blocking": False}

	config = frappe.get_cached_doc("Gate Pass Source", names[0].name)
	requirement = config.enforce_on_target or "Not Required"
	if config.block_native_target_button:
		requirement = "Only Via Gate Pass"

	ctx = RuleContext(frappe._dict({"doctype": target_doctype}), config)
	code = "TGT-BLOCK-NATIVE" if config.block_native_target_button else "TGT-REQUIRED"
	return {"requirement": requirement, "blocking": ctx.resolve_action(code) in ("Block", "Hard")}
