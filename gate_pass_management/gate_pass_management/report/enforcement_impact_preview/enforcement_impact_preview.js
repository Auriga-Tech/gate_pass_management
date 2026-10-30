// Copyright (c) 2026, Auriga IT and contributors
// For license information, please see license.txt

frappe.query_reports["Enforcement Impact Preview"] = {
	filters: [
		{
			fieldname: "days",
			label: __("Look Back (Days)"),
			fieldtype: "Int",
			default: 30,
			reqd: 1,
		},
		{
			fieldname: "preset",
			label: __("If We Switched To"),
			fieldtype: "Select",
			options: "Balanced\nStrict",
			default: "Balanced",
			reqd: 1,
		},
	],
};

// This report answers "what would break if we tightened enforcement".
// It reads history; it changes nothing.
frappe.query_reports["Enforcement Impact Preview"].onload = function (report) {
	report.page.add_inner_message(
		__("This is a simulation over past gate passes. Nothing is changed by running it.")
	);
};
