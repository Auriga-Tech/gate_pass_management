// Gate Pass list view: colour the status column so the yard reads at a glance.
frappe.listview_settings["Gate Pass"] = {
	add_fields: ["status", "direction", "per_processed", "return_status"],

	get_indicator(doc) {
		const colour = (gatepass.STATUS_COLOURS || {})[doc.status] || "gray";
		return [__(doc.status), colour, "status,=," + doc.status];
	},

	onload(listview) {
		listview.page.add_inner_button(__("Yard — Inside Now"), () => {
			listview.filter_area.clear();
			listview.filter_area.add([
				["Gate Pass", "docstatus", "=", 1],
				["Gate Pass", "status", "in", ["Inside", "At Gate", "Partially Processed"]],
			]);
		});
		listview.page.add_inner_button(__("Overdue Returns"), () => {
			listview.filter_area.clear();
			listview.filter_area.add([
				["Gate Pass", "docstatus", "=", 1],
				["Gate Pass", "return_status", "=", "Overdue"],
			]);
		});
	},
};
