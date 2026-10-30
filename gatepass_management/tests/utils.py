"""Test fixtures.

Everything the behavioural tests need, built by the tests themselves. Nothing
here reads data that happens to be on the site: a test that passes only because
someone once ran a demo script is not a test.

Names are prefixed `_GPTEST` so a leftover from an interrupted run is obvious
and can be deleted without wondering what it was.
"""

from __future__ import annotations

import contextlib

import frappe
from frappe.utils import today

PREFIX = "_GPTEST"

ITEM = f"{PREFIX} Widget"
ITEM_B = f"{PREFIX} Bolt"
SUPPLIER = f"{PREFIX} Supplier"
CUSTOMER = f"{PREFIX} Customer"


# ---------------------------------------------------------------- masters


def ensure_masters() -> dict:
	"""Company, warehouses, item and party. Idempotent.

	An existing company is reused rather than creating one: building a company
	drags in a whole chart of accounts, and every site that can run ERPNext
	tests already has one. Only a site with none pays that cost.
	"""
	company = frappe.db.get_value("Company", {}, "name")
	if not company:
		company = _make_company()

	abbr = frappe.db.get_value("Company", company, "abbr")
	stores = _ensure_warehouse("Stores", company, abbr)
	rejected = _ensure_warehouse("Rejected", company, abbr)

	for code in (ITEM, ITEM_B):
		if not frappe.db.exists("Item", code):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": code,
					"item_group": _any_item_group(),
					"stock_uom": "Nos",
					"is_stock_item": 1,
					"is_purchase_item": 1,
					"is_sales_item": 1,
				}
			).insert(ignore_permissions=True)

	if not frappe.db.exists("Supplier", SUPPLIER):
		frappe.get_doc(
			{
				"doctype": "Supplier",
				"supplier_name": SUPPLIER,
				"supplier_group": frappe.db.get_value("Supplier Group", {}, "name"),
			}
		).insert(ignore_permissions=True)

	return {"company": company, "abbr": abbr, "stores": stores, "rejected": rejected}


def ensure_cost_center(masters: dict) -> str:
	"""A leaf cost center that is not the company's default.

	Not the default on purpose: the purchase order already carries the default
	onto the receipt, so a test using it could not tell "the gate pass cost
	center arrived" from "ERPNext's own mapper put it there".
	"""
	name = f"{PREFIX} CC - {masters['abbr']}"
	if not frappe.db.exists("Cost Center", name):
		parent = frappe.db.get_value(
			"Cost Center",
			{"company": masters["company"], "is_group": 1, "parent_cost_center": ["in", ["", None]]},
			"name",
		)
		frappe.get_doc(
			{
				"doctype": "Cost Center",
				"cost_center_name": f"{PREFIX} CC",
				"company": masters["company"],
				"parent_cost_center": parent,
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
	return name


def _make_company() -> str:
	doc = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": f"{PREFIX} Co",
			"abbr": "GPT",
			"default_currency": frappe.db.get_value("Currency", {"enabled": 1}, "name") or "INR",
			"country": frappe.db.get_value("Country", {}, "name") or "India",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def _ensure_warehouse(name: str, company: str, abbr: str) -> str:
	full = f"{name} - {abbr}"
	if not frappe.db.exists("Warehouse", full):
		frappe.get_doc(
			{"doctype": "Warehouse", "warehouse_name": name, "company": company}
		).insert(ignore_permissions=True)
	return full


def _any_item_group() -> str:
	return (
		frappe.db.get_value("Item Group", {"is_group": 0}, "name")
		or frappe.db.get_value("Item Group", {}, "name")
	)


# ------------------------------------------------------------ transactions


def make_purchase_order(masters: dict, lines: list[tuple[str, float]], submit: bool = True):
	"""A submitted Purchase Order, as the usual source document."""
	po = frappe.get_doc(
		{
			"doctype": "Purchase Order",
			"company": masters["company"],
			"supplier": SUPPLIER,
			"transaction_date": today(),
			"schedule_date": today(),
			"items": [
				{
					"item_code": code,
					"qty": qty,
					"rate": 10,
					"warehouse": masters["stores"],
					"schedule_date": today(),
				}
				for code, qty in lines
			],
		}
	)
	po.insert(ignore_permissions=True)
	if submit:
		po.submit()
	return po


def make_gate_pass(masters: dict, *, direction="In", rows=None, submit=False,
                   insert=True, **fields):
	"""A Gate Pass with free-text rows.

	Free text rather than linked items on purpose: a rule being tested should
	fail because of the rule, not because an Item master was missing.

	`insert=False` returns the document unsaved, which is how a deliberately
	invalid one is built: inserting it would raise the very error under test.
	"""
	doc = frappe.get_doc(
		{
			"doctype": "Gate Pass",
			"company": masters["company"],
			"direction": direction,
			"gate_pass_type": "Material",
			"posting_date": today(),
			"party_type": "Supplier",
			"party": SUPPLIER,
			"vehicle_number": "GP-TEST-0001",
			"driver_name": "Test Driver",
			**fields,
		}
	)
	for row in rows or [{"item_name": "Free text thing", "uom": "Nos", "qty": 1}]:
		doc.append("items", {"is_non_stock": 1, "conversion_factor": 1, **row})

	doc.flags.ignore_permissions = True
	if insert:
		doc.insert(ignore_permissions=True)
		if submit:
			doc.submit()
	return doc


def gate_pass_from_source(source_type: str, source_name: str):
	"""Build a Gate Pass through the real mapper, as the UI does."""
	from gatepass_management.api.gate_pass import build_gate_pass

	return build_gate_pass(source_type, source_name)


def source_name_for(source_doctype: str, direction: str = "In") -> str:
	"""The shipped flow for a doctype, found rather than hard-coded.

	The flow names have been renamed once already; a test that spells one out
	breaks for a reason that has nothing to do with what it is testing.
	"""
	name = frappe.db.get_value(
		"Gate Pass Source",
		{"source_doctype": source_doctype, "direction": direction, "enabled": 1},
		"name",
	)
	if not name:
		raise AssertionError(f"no enabled Gate Pass Source for {source_doctype} / {direction}")
	return name


# ----------------------------------------------------------- rule control


@contextlib.contextmanager
def as_user(email: str):
	"""Run a block as another user, restoring the session afterwards."""
	before = frappe.session.user
	frappe.set_user(email)
	try:
		yield
	finally:
		frappe.set_user(before)


def ensure_user(slug: str, roles: list[str]) -> str:
	"""A system user holding exactly `roles` and nothing else.

	Exactly, because that is the point: a guard who happens to be a Purchase
	User proves nothing about whether a guard can pull from a Purchase Order.
	"""
	email = f"{slug}@gatepass.test"
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": slug,
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		)
		user.insert(ignore_permissions=True)

	user.set("roles", [])
	for role in roles:
		user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	frappe.clear_cache(user=email)
	return email


@contextlib.contextmanager
def user_permission(user: str, allow: str, for_value: str):
	"""A User Permission for the duration of a test.

	This is the mechanism a site uses to restrict a guard to one company or one
	location, and the one the source-access relaxation must keep honouring.
	"""
	doc = frappe.get_doc(
		{"doctype": "User Permission", "user": user, "allow": allow, "for_value": for_value}
	)
	doc.insert(ignore_permissions=True)
	frappe.cache.hdel("user_permissions", user)
	try:
		yield
	finally:
		frappe.delete_doc("User Permission", doc.name, ignore_permissions=True, force=True)
		frappe.cache.hdel("user_permissions", user)


@contextlib.contextmanager
def rule_action(code: str, action: str, threshold=None):
	"""Force one rule to a known action for the duration of a test.

	The shipped preset is Advisory, where most rules only warn. A test asserting
	that something blocks has to say so, or it is really testing the preset.
	"""
	settings = frappe.get_single("Gate Pass Settings")
	row = next((r for r in settings.rules if r.rule_code == code), None)
	if row is None:
		raise AssertionError(f"{code} is not in the Gate Pass Settings rule table")

	before_action, before_threshold = row.action, row.threshold
	row.db_set("action", action, update_modified=False)
	if threshold is not None:
		row.db_set("threshold", threshold, update_modified=False)
	frappe.clear_cache()

	try:
		yield
	finally:
		row.db_set("action", before_action, update_modified=False)
		row.db_set("threshold", before_threshold, update_modified=False)
		frappe.clear_cache()


@contextlib.contextmanager
def setting(**values):
	"""Temporarily change Gate Pass Settings fields."""
	settings = frappe.get_single("Gate Pass Settings")
	before = {k: settings.get(k) for k in values}
	for k, v in values.items():
		settings.db_set(k, v, update_modified=False)
	frappe.clear_cache()
	try:
		yield
	finally:
		for k, v in before.items():
			settings.db_set(k, v, update_modified=False)
		frappe.clear_cache()


def violations_for(doc, at_submit: bool = False) -> dict[str, list]:
	"""Run the validation suite without raising, and report what fired.

	Returns {"block": [codes], "warn": [codes]} so a test can assert on the
	outcome of one rule without being thrown by another.
	"""
	from gatepass_management.gate_pass_management.doctype.gate_pass import validations
	from gatepass_management.rules.engine import RuleContext

	# Same preparation the controller does, so the rules see the derived fields
	# they actually read rather than a half-built document.
	doc.derive_fields()

	ctx = RuleContext(doc, doc.source_config if doc.get("source_type") else None)
	validations.run(doc, ctx, at_submit=at_submit)
	return {
		"block": [v.code for v in ctx.violations],
		"warn": [v.code for v in ctx.warnings],
		"messages": {v.code: v.message for v in ctx.violations + ctx.warnings},
	}
