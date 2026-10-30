// Copyright (c) 2026, Auriga IT and contributors
// For license information, please see license.txt

frappe.query_reports["Gate Pass Register"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "location",
			label: __("Location"),
			fieldtype: "Link",
			options: "Gate Pass Location",
		},
		{
			fieldname: "direction",
			label: __("Direction"),
			fieldtype: "Select",
			options: "\nIn\nOut",
		},
		{
			fieldname: "party_type",
			label: __("Party Type"),
			fieldtype: "Link",
			options: "DocType",
			get_query: () => ({ filters: { name: ["in", ["Supplier", "Customer", "Company", "Employee", "Contact"]] } }),
			on_change() {
				frappe.query_report.set_filter_value("party", "");
				const f = frappe.query_report.get_filter("party");
				if (f) {
					f.df.options = frappe.query_report.get_filter_value("party_type") || "Supplier";
					f.refresh();
				}
			},
		},
		{
			fieldname: "party",
			label: __("Party"),
			fieldtype: "Dynamic Link",
			get_options() {
				return frappe.query_report.get_filter_value("party_type") || "Supplier";
			},
		},
		{
			fieldname: "gate",
			label: __("Gate"),
			fieldtype: "Link",
			options: "Gate",
		},
		{
			fieldname: "vehicle_number",
			label: __("Vehicle Number"),
			fieldtype: "Data",
		},
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nDraft\nAt Gate\nInside\nPartially Processed\nCompleted\nPending Return\nPartially Returned\nReturned\nOverdue Return\nClosed\nCancelled",
		},
		{
			fieldname: "created_by",
			label: __("Created By"),
			fieldtype: "Link",
			options: "User",
		},
	],
};
