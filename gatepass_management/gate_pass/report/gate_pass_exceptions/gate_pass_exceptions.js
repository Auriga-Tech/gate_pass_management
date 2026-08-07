// Copyright (c) 2026, Auriga IT and contributors
// For license information, please see license.txt

frappe.query_reports["Gate Pass Exceptions"] = {
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
			fieldname: "rule_code",
			label: __("Rule Code"),
			fieldtype: "Data",
		},
		{
			fieldname: "event",
			label: __("Event"),
			fieldtype: "Select",
			options: "\nRule Warned\nValidation Failed\nCompliance Overridden\nTimestamp Amended\nDiscrepancy Recorded\nTarget Creation Failed\nAttachment Removed",
			default: "Rule Warned",
		},
		{
			fieldname: "user",
			label: __("User"),
			fieldtype: "Link",
			options: "User",
		},
	],
};
