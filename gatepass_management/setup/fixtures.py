"""Shipped configuration.

A fresh install must produce a working gate pass with no setup at all — that is
the difference between an app people try and an app people abandon. These twelve
flows cover what a manufacturing or distribution site actually does at its gate.

Every one of them is data, not code. An implementer duplicates a record and
edits fields; they never open a Python file.
"""

from __future__ import annotations

import frappe

# ===========================================================================
# Custom fields on ERPNext DocTypes
#
# Namespaced `gate_pass*` rather than `custom_*`: an app-owned field should
# carry the app's identity, and this avoids colliding with the `custom_gate_pass`
# fields that exist on sites migrating from an earlier in-house implementation.
# ===========================================================================

_GATE_PASS_LINK = {
	"fieldname": "gate_pass",
	"fieldtype": "Link",
	"label": "Gate Pass",
	"options": "Gate Pass",
	"insert_after": "company",
	"search_index": 1,
	"no_copy": 1,
}

_GATE_PASS_ITEM_LINK = {
	"fieldname": "gate_pass_item",
	"fieldtype": "Data",
	"label": "Gate Pass Item Row",
	"read_only": 1,
	"hidden": 1,
	"no_copy": 1,
	"print_hide": 1,
}

CUSTOM_FIELDS = {
	"Purchase Receipt": [
		dict(_GATE_PASS_LINK, insert_after="supplier"),
		{
			"fieldname": "gate_pass_tracking_id",
			"fieldtype": "Data",
			"label": "Gate Pass Tracking ID",
			"insert_after": "gate_pass",
			"fetch_from": "gate_pass.tracking_id",
			"read_only": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "gate_pass_reference_no",
			"fieldtype": "Data",
			"label": "Gate Pass Invoice / Challan No",
			"insert_after": "gate_pass_tracking_id",
			"fetch_from": "gate_pass.reference_no",
			"read_only": 1,
			"no_copy": 1,
		},
		{
			"fieldname": "gate_pass_vehicle_photo",
			"fieldtype": "Attach Image",
			"label": "Vehicle Photo (from Gate Pass)",
			"insert_after": "gate_pass_reference_no",
			"fetch_from": "gate_pass.vehicle_photo",
			"read_only": 1,
			"no_copy": 1,
		},
	],
	"Purchase Receipt Item": [dict(_GATE_PASS_ITEM_LINK, insert_after="uom")],
	"Purchase Invoice": [
		dict(_GATE_PASS_LINK, insert_after="supplier"),
		{
			"fieldname": "gate_pass_tracking_id",
			"fieldtype": "Data",
			"label": "Gate Pass Tracking ID",
			"insert_after": "gate_pass",
			"fetch_from": "gate_pass.tracking_id",
			"read_only": 1,
			"no_copy": 1,
		},
	],
	"Subcontracting Receipt": [
		dict(_GATE_PASS_LINK, insert_after="supplier"),
	],
	"Subcontracting Receipt Item": [dict(_GATE_PASS_ITEM_LINK, insert_after="stock_uom")],
	"Stock Entry": [dict(_GATE_PASS_LINK, insert_after="company")],
	"Stock Entry Detail": [dict(_GATE_PASS_ITEM_LINK, insert_after="uom")],
	"Delivery Note": [dict(_GATE_PASS_LINK, insert_after="customer")],
	"Delivery Note Item": [dict(_GATE_PASS_ITEM_LINK, insert_after="uom")],
	"Sales Invoice": [dict(_GATE_PASS_LINK, insert_after="customer")],
	"Purchase Order": [
		{
			"fieldname": "gate_pass_status",
			"fieldtype": "Select",
			"label": "Gate Pass Status",
			"options": "\nNot Started\nPartial\nComplete",
			"insert_after": "status",
			"read_only": 1,
			"no_copy": 1,
			"allow_on_submit": 1,
		}
	],
	"Subcontracting Order": [
		{
			"fieldname": "gate_pass_status",
			"fieldtype": "Select",
			"label": "Gate Pass Status",
			"options": "\nNot Started\nPartial\nComplete",
			"insert_after": "status",
			"read_only": 1,
			"no_copy": 1,
			"allow_on_submit": 1,
		}
	],
	"Item": [
		{
			"fieldname": "exclude_from_gate_pass",
			"fieldtype": "Check",
			"label": "Exclude from Gate Pass",
			"insert_after": "is_stock_item",
			"description": "For services and non-physical items that never cross the gate.",
		}
	],
}


# ===========================================================================
# The twelve shipped flows
# ===========================================================================

STANDARD_SOURCES = [
	{
		"source_name": "Purchase Order - Inward",
		"button_label": "Purchase Order",
		"direction": "In",
		"sequence": 10,
		"source_doctype": "Purchase Order",
		"child_table": "items",
		"item_field": "item_code",
		"qty_field": "qty",
		"consumed_field": "received_qty",
		"uom_field": "uom",
		"rate_field": "rate",
		"warehouse_field": "warehouse",
		"pending_formula": "qty - max(received, consumed)",
		"party_type": "Supplier",
		"party_field": "supplier",
		"source_filters": '{"docstatus": 1}',
		"allowed_statuses": "To Receive and Bill, To Receive",
		"allow_row_selection": 1,
		"row_columns": "item_code,item_name,qty,received_qty",
		"qty_policy": "Editable",
		"allow_discrepancy": 1,
		"target_doctype": "Purchase Receipt",
		"target_creation_mode": "Manual Button",
		"copy_attachments_to_target": 1,
		"enforce_on_target": "Not Required",
		"description": "Goods received against a purchase order.",
		"checklist": [
			{"document_name": "Invoice / Challan Copy", "is_mandatory": 1, "action": "Block"},
			{"document_name": "Transporter LR / Builty", "is_mandatory": 0, "action": "Warn"},
		],
	},
	{
		"source_name": "Subcontracting Order - Finished Goods Inward",
		"button_label": "Subcontract Order (Finished Goods)",
		"direction": "In",
		"sequence": 20,
		"source_doctype": "Subcontracting Order",
		"sub_type": "Finished Goods",
		"child_table": "items",
		"item_field": "item_code",
		"qty_field": "qty",
		"consumed_field": "received_qty",
		"uom_field": "stock_uom",
		"rate_field": "rate",
		"warehouse_field": "warehouse",
		"bom_field": "bom",
		"pending_formula": "qty - max(received, consumed)",
		"party_type": "Supplier",
		"party_field": "supplier",
		"source_filters": '{"docstatus": 1}',
		"allowed_statuses": "Material Transferred, Partial Material Transferred, Partially Received",
		"allow_row_selection": 1,
		"row_columns": "item_code,item_name,qty,received_qty",
		"qty_policy": "Editable",
		"allow_discrepancy": 1,
		"target_doctype": "Subcontracting Receipt",
		"target_creation_mode": "Manual Button",
		"description": "Finished goods back from a subcontractor.",
	},
	{
		"source_name": "Subcontracting Order - Raw Material Outward",
		"button_label": "Subcontract Order (Raw Material)",
		"direction": "Out",
		"sequence": 30,
		"source_doctype": "Subcontracting Order",
		"sub_type": "Raw Material Return",
		"child_table": "supplied_items",
		"item_field": "rm_item_code",
		"qty_field": "required_qty",
		"uom_field": "stock_uom",
		"rate_field": "rate",
		# Supplied items carry `reserve_warehouse`, not `warehouse`.
		"warehouse_field": "reserve_warehouse",
		"pending_formula": "qty - consumed",
		"party_type": "Supplier",
		"party_field": "supplier",
		"source_filters": '{"docstatus": 1}',
		"allow_row_selection": 1,
		"row_columns": "rm_item_code,required_qty",
		"qty_policy": "Editable",
		"allow_discrepancy": 1,
		"description": "Raw material sent to a subcontractor.",
	},
	{
		"source_name": "Stock Entry - Send to Subcontractor",
		"button_label": "Stock Entry (Subcontract)",
		"direction": "Out",
		"sequence": 40,
		"source_doctype": "Stock Entry",
		"sub_type": "Send to Subcontractor",
		"child_table": "items",
		"item_field": "item_code",
		"qty_field": "qty",
		"uom_field": "uom",
		"rate_field": "basic_rate",
		"warehouse_field": "s_warehouse",
		"pending_formula": "qty - consumed",
		"party_type": "From Field",
		"party_field": "subcontracting_order.supplier",
		"source_filters": '{"docstatus": 1, "stock_entry_type": "Send to Subcontractor"}',
		"qty_policy": "Locked to Source",
		"allow_discrepancy": 1,
		"auto_create_draft": 1,
		"auto_create_condition": "doc.stock_entry_type == 'Send to Subcontractor'",
		"auto_create_assign_to_role": "Gate Pass Operator",
		"description": "Material sent to a subcontractor.",
	},
	{
		"source_name": "Stock Entry - Transit Outward",
		"button_label": "Stock Entry (Transfer Out)",
		"direction": "Out",
		"sequence": 50,
		"source_doctype": "Stock Entry",
		"sub_type": "Material Transfer",
		"child_table": "items",
		"item_field": "item_code",
		"qty_field": "qty",
		"uom_field": "uom",
		"rate_field": "basic_rate",
		"warehouse_field": "s_warehouse",
		"pending_formula": "qty - consumed",
		"party_type": "Company",
		"source_filters": '{"docstatus": 1, "stock_entry_type": "Material Transfer"}',
		"qty_policy": "Locked to Source",
		"allow_discrepancy": 1,
		"auto_create_draft": 1,
		"auto_create_condition": "doc.add_to_transit == 1",
		"auto_create_assign_to_role": "Gate Pass Operator",
		"description": "Material sent to another plant or branch.",
	},
	{
		"source_name": "Stock Entry - Transit Inward",
		"button_label": "Stock Entry (Transfer In)",
		"direction": "In",
		"sequence": 60,
		"source_doctype": "Stock Entry",
		"sub_type": "Transit Receipt",
		"child_table": "items",
		"item_field": "item_code",
		"qty_field": "qty",
		"uom_field": "uom",
		"rate_field": "basic_rate",
		"warehouse_field": "t_warehouse",
		"pending_formula": "qty - consumed",
		"party_type": "Company",
		"source_filters": '{"docstatus": 1}',
		"qty_policy": "Prefilled, Editable",
		"allow_discrepancy": 1,
		"description": "Material received from another plant or branch.",
	},
	{
		"source_name": "Stock Entry - Manual Return Inward",
		"button_label": "Return of Transfer",
		"direction": "In",
		"sequence": 70,
		"source_doctype": "Stock Entry",
		"sub_type": "Manual Return",
		"child_table": "items",
		"item_field": "item_code",
		"qty_field": "qty",
		"uom_field": "uom",
		"rate_field": "basic_rate",
		"warehouse_field": "t_warehouse",
		"pending_formula": "qty - consumed",
		"party_type": "Company",
		"source_filters": '{"docstatus": 1}',
		"qty_policy": "Editable",
		"allow_discrepancy": 1,
		"description": "Material returned before a return entry exists.",
	},
	{
		"source_name": "Purchase Receipt - Return Outward",
		"button_label": "Purchase Receipt (Return)",
		"direction": "Out",
		"sequence": 80,
		"source_doctype": "Purchase Receipt",
		"sub_type": "Return of Goods",
		"child_table": "items",
		"item_field": "item_code",
		"qty_field": "qty",
		"uom_field": "uom",
		"rate_field": "rate",
		"warehouse_field": "warehouse",
		"pending_formula": "abs(qty) - consumed",
		"party_type": "Supplier",
		"party_field": "supplier",
		"source_filters": '{"docstatus": 1, "is_return": 1}',
		"qty_policy": "Editable",
		"allow_discrepancy": 0,
		"description": "Rejected goods sent back to the supplier.",
		"compliance_rules": [
			{"check_code": "IN_E_WAY_BILL", "label": "E-Way Bill",
			 "required_when": "From Provider", "action": "Ignore",
			 "threshold_source": "From Provider", "recheck_on_submit": 1,
			 "require_override_reason": 1},
		],
	},
	{
		"source_name": "Subcontracting Receipt - Return Outward",
		"button_label": "Subcontract Receipt (Return)",
		"direction": "Out",
		"sequence": 90,
		"source_doctype": "Subcontracting Receipt",
		"sub_type": "Finished Goods Return",
		"description": "Finished goods sent back for rework.",
		"child_table": "items",
		"item_field": "item_code",
		"qty_field": "qty",
		"uom_field": "stock_uom",
		"rate_field": "rate",
		"warehouse_field": "warehouse",
		"pending_formula": "abs(qty) - consumed",
		"party_type": "Supplier",
		"party_field": "supplier",
		"source_filters": '{"docstatus": 1, "is_return": 1}',
		"qty_policy": "Editable",
		"allow_discrepancy": 0,
	},
	{
		"source_name": "Sales Invoice - Dispatch",
		"button_label": "Sales Invoice",
		"direction": "Out",
		"sequence": 100,
		"source_doctype": "Sales Invoice",
		"child_table": "items",
		"item_field": "item_code",
		"qty_field": "qty",
		"uom_field": "uom",
		"rate_field": "rate",
		"warehouse_field": "warehouse",
		"pending_formula": "qty - consumed",
		"party_type": "Customer",
		"party_field": "customer",
		"source_filters": '{"docstatus": 1, "update_stock": 1}',
		"qty_policy": "Locked to Source",
		"allow_discrepancy": 0,
		"description": "Dispatch against a tax invoice.",
		"compliance_rules": [
			{"check_code": "IN_E_INVOICE", "label": "E-Invoice (IRN)",
			 "required_when": "From Provider", "action": "Ignore",
			 "threshold_source": "From Provider", "recheck_on_submit": 1,
			 "require_override_reason": 1},
			{"check_code": "IN_E_WAY_BILL", "label": "E-Way Bill",
			 "required_when": "From Provider", "action": "Ignore",
			 "threshold_source": "From Provider", "recheck_on_submit": 1,
			 "require_override_reason": 1},
		],
		"checklist": [
			{"document_name": "Signed Invoice Copy", "is_mandatory": 0, "action": "Warn"},
		],
	},
	{
		"source_name": "Delivery Note - Dispatch",
		"button_label": "Delivery Note",
		"direction": "Out",
		"sequence": 110,
		"source_doctype": "Delivery Note",
		"description": "Dispatch against a delivery note.",
		"child_table": "items",
		"item_field": "item_code",
		"qty_field": "qty",
		"uom_field": "uom",
		"rate_field": "rate",
		"warehouse_field": "warehouse",
		"pending_formula": "qty - consumed",
		"party_type": "Customer",
		"party_field": "customer",
		"source_filters": '{"docstatus": 1, "is_return": 0}',
		"qty_policy": "Locked to Source",
		"allow_discrepancy": 0,
		"compliance_rules": [
			{"check_code": "IN_E_WAY_BILL", "label": "E-Way Bill",
			 "required_when": "From Provider", "action": "Ignore",
			 "threshold_source": "From Provider", "recheck_on_submit": 1,
			 "require_override_reason": 1},
		],
	},
	{
		"source_name": "Gate Pass - Return Leg Inward",
		"button_label": "Returnable Gate Pass",
		"direction": "In",
		"sequence": 120,
		"source_doctype": "Gate Pass",
		"sub_type": "Return Leg",
		"child_table": "items",
		"item_field": "item_code",
		"qty_field": "qty",
		"uom_field": "uom",
		"rate_field": "rate",
		"warehouse_field": "warehouse",
		"pending_formula": "qty - consumed",
		"party_type": "From Field",
		"party_field": "party",
		"source_filters": '{"docstatus": 1, "direction": "Out", "is_returnable": 1}',
		"qty_policy": "Prefilled, Editable",
		"allow_discrepancy": 1,
		"description": "Items coming back on a returnable outward pass.",
	},
]


def seed_sources():
	"""Insert or reconcile the standard flows.

	Standard records are refreshed on migrate so improvements reach existing
	sites — but only the fields that describe *how the mapping works*. Anything
	a customer would reasonably tune (enforcement, checklists, compliance
	actions) is written on first insert and never touched again.
	"""
	from gatepass_management.utils.logger import get_logger

	refreshable = {
		"button_label", "child_table", "item_field", "qty_field", "consumed_field",
		"uom_field", "rate_field", "warehouse_field", "bom_field", "pending_formula",
		"party_type", "party_field", "row_columns", "sequence", "description",
	}

	created = 0
	for spec in STANDARD_SOURCES:
		name = spec["source_name"]
		children = {
			"checklist": spec.pop("checklist", None),
			"compliance_rules": spec.pop("compliance_rules", None),
		}

		if frappe.db.exists("Gate Pass Source", name):
			doc = frappe.get_doc("Gate Pass Source", name)
			if not doc.is_standard:
				# The customer has taken ownership of this record. Leave it be.
				_restore(spec, children)
				continue
			for field in refreshable:
				if field in spec:
					doc.set(field, spec[field])
			doc.flags.ignore_permissions = True
			doc.save(ignore_permissions=True)
			_restore(spec, children)
			continue

		doc = frappe.get_doc({"doctype": "Gate Pass Source", "is_standard": 1, **spec})
		for table, rows in children.items():
			for row in rows or []:
				doc.append(table, row)
		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		created += 1
		_restore(spec, children)

	if created:
		get_logger().info("sources_seeded", extra={"created": created})


def _restore(spec, children):
	for key, value in children.items():
		if value is not None:
			spec[key] = value


def seed_masters():
	"""Discrepancy reasons, so the Discrepancy Register is useful on day one."""
	reasons = [
		("Short Delivered", "Shortage", "Supplier"),
		("Lost in Transit", "Shortage", "Transporter"),
		("Damaged in Transit", "Damage", "Transporter"),
		("Damaged Packaging", "Damage", "Supplier"),
		("Wrong Item Supplied", "Rejection", "Supplier"),
		("Quality Rejected at Gate", "Rejection", "Supplier"),
		("Documents Missing", "Documentation", "Supplier"),
		("Counting Difference", "Shortage", "Unknown"),
	]
	for reason, category, liable in reasons:
		if frappe.db.exists("Gate Pass Discrepancy Reason", reason):
			continue
		frappe.get_doc(
			{
				"doctype": "Gate Pass Discrepancy Reason",
				"reason": reason,
				"category": category,
				"liable_party": liable,
				"is_active": 1,
			}
		).insert(ignore_permissions=True)
