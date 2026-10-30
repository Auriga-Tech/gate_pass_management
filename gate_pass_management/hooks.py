app_name = "gate_pass_management"
app_title = "Gate Pass Management"
app_publisher = "Auriga IT"
app_description = "Control every material movement at the gate. Gate passes for inward and outward movement, reconciled against ERPNext documents."
app_email = "erp@aurigait.com"
app_license = "gpl-3.0"

required_apps = ["frappe/erpnext"]

# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------

app_include_js = "gate_pass_management.bundle.js"
app_include_css = "gate_pass_management.bundle.css"

doctype_js = {
	"Gate Pass": "public/js/gate_pass.js",
	"Gate Pass Settings": "public/js/gate_pass_settings.js",
	"Gate Pass Source": "public/js/gate_pass_source.js",
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

after_install = "gate_pass_management.setup.install.after_install"
after_migrate = "gate_pass_management.setup.install.after_migrate"
before_uninstall = "gate_pass_management.setup.install.before_uninstall"

# ---------------------------------------------------------------------------
# Document events
#
# Every handler below returns immediately when the app is disabled or the
# document predates Gate Pass Settings.enforce_from_date. See
# gate_pass_management.utils.guards.is_active().
# ---------------------------------------------------------------------------

doc_events = {
	"Purchase Receipt": {
		"validate": "gate_pass_management.targets.guards.validate_target",
		"before_submit": "gate_pass_management.targets.guards.before_submit_target",
		"on_submit": "gate_pass_management.targets.guards.on_submit_target",
		"on_cancel": "gate_pass_management.targets.guards.on_cancel_target",
		"on_trash": "gate_pass_management.targets.guards.on_trash_target",
	},
	"Subcontracting Receipt": {
		"validate": "gate_pass_management.targets.guards.validate_target",
		"before_submit": "gate_pass_management.targets.guards.before_submit_target",
		"on_submit": "gate_pass_management.targets.guards.on_submit_target",
		"on_cancel": "gate_pass_management.targets.guards.on_cancel_target",
		"on_trash": "gate_pass_management.targets.guards.on_trash_target",
	},
	"Stock Entry": {
		"validate": "gate_pass_management.targets.guards.validate_target",
		"before_submit": "gate_pass_management.targets.guards.before_submit_target",
		"on_submit": [
			"gate_pass_management.targets.guards.on_submit_target",
			"gate_pass_management.sources.automation.auto_create_draft",
		],
		"on_cancel": "gate_pass_management.targets.guards.on_cancel_target",
		"on_trash": "gate_pass_management.targets.guards.on_trash_target",
	},
	"Delivery Note": {
		"validate": "gate_pass_management.targets.guards.validate_target",
		"before_submit": "gate_pass_management.targets.guards.before_submit_target",
		"on_submit": "gate_pass_management.targets.guards.on_submit_target",
		"on_cancel": "gate_pass_management.targets.guards.on_cancel_target",
		"on_trash": "gate_pass_management.targets.guards.on_trash_target",
	},
	"Sales Invoice": {
		"validate": "gate_pass_management.targets.guards.validate_target",
		"before_submit": "gate_pass_management.targets.guards.before_submit_target",
		"on_submit": "gate_pass_management.targets.guards.on_submit_target",
		"on_cancel": "gate_pass_management.targets.guards.on_cancel_target",
		"on_trash": "gate_pass_management.targets.guards.on_trash_target",
	},
	"Purchase Order": {
		"on_submit": "gate_pass_management.sources.automation.auto_create_draft",
	},
	"File": {
		"on_trash": "gate_pass_management.gate_pass_management.doctype.gate_pass.attachments.prevent_delete_on_submit",
	},
}

# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

permission_query_conditions = {
	"Gate Pass": "gate_pass_management.utils.permissions.gate_pass_query_conditions",
}

has_permission = {
	"Gate Pass": "gate_pass_management.utils.permissions.gate_pass_has_permission",
}

# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------

# One function per doctype: Frappe gives a dashboard override only the dashboard
# data, never the doctype, and the Gate Pass link back is a Dynamic Link that
# needs to know which doctype it is resolving.
override_doctype_dashboards = {
	"Purchase Order": "gate_pass_management.utils.dashboards.get_purchase_order_dashboard",
	"Subcontracting Order": "gate_pass_management.utils.dashboards.get_subcontracting_order_dashboard",
	"Purchase Receipt": "gate_pass_management.utils.dashboards.get_purchase_receipt_dashboard",
	"Subcontracting Receipt": "gate_pass_management.utils.dashboards.get_subcontracting_receipt_dashboard",
	"Stock Entry": "gate_pass_management.utils.dashboards.get_stock_entry_dashboard",
	"Delivery Note": "gate_pass_management.utils.dashboards.get_delivery_note_dashboard",
	"Sales Invoice": "gate_pass_management.utils.dashboards.get_sales_invoice_dashboard",
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
	"gate_pass_management.compliance.providers.india.PROVIDER",
]

# ---------------------------------------------------------------------------
# Scheduled tasks
# ---------------------------------------------------------------------------

scheduler_events = {
	"daily": [
		"gate_pass_management.gate_pass_management.doctype.gate_pass.scheduler.flag_overdue_returns",
		"gate_pass_management.gate_pass_management.doctype.gate_pass.scheduler.refresh_statuses",
		"gate_pass_management.gate_pass_management.doctype.gate_pass.scheduler.flag_stale_drafts",
		"gate_pass_management.gate_pass_management.doctype.gate_pass_event_log.retention.purge_expired",
		"gate_pass_management.sources.automation.expire_unclaimed_drafts",
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
		"gate_pass_management.utils.jinja.get_compliance_summary",
		"gate_pass_management.utils.jinja.get_qr_code",
	],
}
