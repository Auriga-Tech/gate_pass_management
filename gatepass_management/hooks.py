app_name = "gatepass_management"
app_title = "Gate Pass Management"
app_publisher = "Auriga IT"
app_description = "Control every material movement at the gate. Gate passes for inward and outward movement, reconciled against ERPNext documents."
app_email = "info@aurigait.com"
app_license = "gpl-3.0"

required_apps = ["frappe/erpnext"]

# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

app_include_js = "gatepass_management.bundle.js"
app_include_css = "gatepass_management.bundle.css"

doctype_js = {
	"Gate Pass": "public/js/gate_pass.js",
	"Purchase Order": "public/js/source_forms/purchase_order.js",
	"Subcontracting Order": "public/js/source_forms/subcontracting_order.js",
	"Stock Entry": "public/js/source_forms/stock_entry.js",
	"Delivery Note": "public/js/source_forms/delivery_note.js",
	"Sales Invoice": "public/js/source_forms/sales_invoice.js",
	"Purchase Receipt": "public/js/target_forms/purchase_receipt.js",
	"Subcontracting Receipt": "public/js/target_forms/subcontracting_receipt.js",
}

doctype_list_js = {"Gate Pass": "public/js/gate_pass_list.js"}

# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------

after_install = "gatepass_management.setup.install.after_install"
after_migrate = "gatepass_management.setup.install.after_migrate"
before_uninstall = "gatepass_management.setup.install.before_uninstall"

# ---------------------------------------------------------------------------
# Document events
#
# Every handler below returns immediately when the app is disabled or the
# document predates Gate Pass Settings.enforce_from_date. See
# gatepass_management.utils.guards.is_active().
# ---------------------------------------------------------------------------

doc_events = {
	"Purchase Receipt": {
		"validate": "gatepass_management.targets.guards.validate_target",
		"before_submit": "gatepass_management.targets.guards.before_submit_target",
		"on_submit": "gatepass_management.targets.guards.on_submit_target",
		"on_cancel": "gatepass_management.targets.guards.on_cancel_target",
		"on_trash": "gatepass_management.targets.guards.on_trash_target",
	},
	"Subcontracting Receipt": {
		"validate": "gatepass_management.targets.guards.validate_target",
		"before_submit": "gatepass_management.targets.guards.before_submit_target",
		"on_submit": "gatepass_management.targets.guards.on_submit_target",
		"on_cancel": "gatepass_management.targets.guards.on_cancel_target",
		"on_trash": "gatepass_management.targets.guards.on_trash_target",
	},
	"Stock Entry": {
		"validate": "gatepass_management.targets.guards.validate_target",
		"before_submit": "gatepass_management.targets.guards.before_submit_target",
		"on_submit": [
			"gatepass_management.targets.guards.on_submit_target",
			"gatepass_management.sources.automation.auto_create_draft",
		],
		"on_cancel": "gatepass_management.targets.guards.on_cancel_target",
		"on_trash": "gatepass_management.targets.guards.on_trash_target",
	},
	"Delivery Note": {
		"validate": "gatepass_management.targets.guards.validate_target",
		"before_submit": "gatepass_management.targets.guards.before_submit_target",
		"on_submit": "gatepass_management.targets.guards.on_submit_target",
		"on_cancel": "gatepass_management.targets.guards.on_cancel_target",
		"on_trash": "gatepass_management.targets.guards.on_trash_target",
	},
	"Sales Invoice": {
		"validate": "gatepass_management.targets.guards.validate_target",
		"before_submit": "gatepass_management.targets.guards.before_submit_target",
		"on_submit": "gatepass_management.targets.guards.on_submit_target",
		"on_cancel": "gatepass_management.targets.guards.on_cancel_target",
		"on_trash": "gatepass_management.targets.guards.on_trash_target",
	},
	"Purchase Order": {
		"on_submit": "gatepass_management.sources.automation.auto_create_draft",
	},
	"File": {
		"on_trash": "gatepass_management.gate_pass_management.doctype.gate_pass.attachments.prevent_delete_on_submit",
	},
}

# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

permission_query_conditions = {
	"Gate Pass": "gatepass_management.utils.permissions.gate_pass_query_conditions",
}

has_permission = {
	"Gate Pass": "gatepass_management.utils.permissions.gate_pass_has_permission",
}

# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------

override_doctype_dashboards = {
	"Purchase Order": "gatepass_management.utils.dashboards.get_purchase_order_dashboard",
	"Subcontracting Order": "gatepass_management.utils.dashboards.get_subcontracting_order_dashboard",
	"Purchase Receipt": "gatepass_management.utils.dashboards.get_purchase_receipt_dashboard",
	"Subcontracting Receipt": "gatepass_management.utils.dashboards.get_subcontracting_receipt_dashboard",
	"Stock Entry": "gatepass_management.utils.dashboards.get_stock_entry_dashboard",
	"Delivery Note": "gatepass_management.utils.dashboards.get_delivery_note_dashboard",
	"Sales Invoice": "gatepass_management.utils.dashboards.get_sales_invoice_dashboard",
}

# ---------------------------------------------------------------------------
# Compliance providers
#
# Any app may register statutory checks by appending to this hook. A provider
# is a module exposing PROVIDER (a ComplianceProvider instance). Providers that
# depend on an app which is not installed must self-disable by returning
# NOT_APPLICABLE — never raise.
# ---------------------------------------------------------------------------

gate_pass_compliance_providers = [
	"gatepass_management.compliance.providers.india.PROVIDER",
]

# ---------------------------------------------------------------------------
# Scheduled tasks
# ---------------------------------------------------------------------------

scheduler_events = {
	"daily": [
		"gatepass_management.gate_pass_management.doctype.gate_pass.scheduler.flag_overdue_returns",
		"gatepass_management.gate_pass_management.doctype.gate_pass.scheduler.refresh_statuses",
		"gatepass_management.gate_pass_management.doctype.gate_pass_event_log.retention.purge_expired",
		"gatepass_management.sources.automation.expire_unclaimed_drafts",
	],
}

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

# Gate Pass links are handled explicitly by targets.guards; keep Frappe's
# generic link check out of the way so our own messages surface instead.
ignore_links_on_delete = ["Gate Pass Event Log"]

export_python_type_annotations = True

jinja = {
	"methods": [
		"gatepass_management.utils.jinja.get_compliance_summary",
		"gatepass_management.utils.jinja.get_qr_code",
	],
}
