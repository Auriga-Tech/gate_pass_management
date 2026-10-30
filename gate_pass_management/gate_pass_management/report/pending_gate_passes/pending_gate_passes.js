// Copyright (c) 2026, Auriga IT and contributors
// For license information, please see license.txt

frappe.query_reports["Pending Gate Passes"] = {
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
			fieldname: "direction",
			label: __("Direction"),
			fieldtype: "Select",
			options: "\nIn\nOut",
		},
		{
			fieldname: "source_type",
			label: __("Source Flow"),
			fieldtype: "Link",
			options: "Gate Pass Source",
		},
		{
			fieldname: "min_age",
			label: __("Pending At Least (Days)"),
			fieldtype: "Int",
			default: 0,
		},
	],
};

// Age is the point of this report, so make it impossible to miss.
frappe.query_reports["Pending Gate Passes"].formatter = function (value, row, column, data, default_formatter) {
	value = default_formatter(value, row, column, data);
	if (column.fieldname === "age_days" && data) {
		const age = cint(data.age_days);
		if (age >= 7) value = `<span style="color:var(--red-600);font-weight:600">${value}</span>`;
		else if (age >= 4) value = `<span style="color:var(--orange-600);font-weight:600">${value}</span>`;
		else if (age >= 2) value = `<span style="color:var(--yellow-700)">${value}</span>`;
	}
	return value;
};
