// Copyright (c) 2026, Auriga IT and contributors
// For license information, please see license.txt

frappe.query_reports["Vehicle Movement"] = {
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
			fieldname: "vehicle_number",
			label: __("Vehicle Number"),
			fieldtype: "Data",
		},
		{
			fieldname: "transporter",
			label: __("Transporter"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "group_by_vehicle",
			label: __("Summarise by Vehicle"),
			fieldtype: "Check",
			default: 0,
		},
	],
};
