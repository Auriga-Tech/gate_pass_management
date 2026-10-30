// Copyright (c) 2026, Auriga IT and contributors
// For license information, please see license.txt

frappe.query_reports["Pending Returnable Gate Passes"] = {
	filters: [
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
			fieldname: "only_overdue",
			label: __("Only Overdue"),
			fieldtype: "Check",
			default: 0,
		},
	],
};

frappe.query_reports["Pending Returnable Gate Passes"].formatter = function (value, row, column, data, default_formatter) {
	value = default_formatter(value, row, column, data);
	if (column.fieldname === "days_overdue" && data && cint(data.days_overdue) > 0) {
		value = `<span style="color:var(--red-600);font-weight:600">${value}</span>`;
	}
	return value;
};
