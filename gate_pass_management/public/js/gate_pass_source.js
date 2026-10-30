// Gate Pass Source.
//
// The Compliance Checks grid had its Check field hard-coded to the two India
// codes, so a provider registered through the gate_pass_compliance_providers
// hook could never be selected — the framework was extensible, the form was not.
// Options now come from whatever providers are actually installed.

frappe.ui.form.on("Gate Pass Source", {
	refresh(frm) {
		frm.trigger("load_compliance_checks");

		if (!frm.is_new() && frm.doc.is_standard) {
			frm.dashboard.add_comment(
				__(
					"This is a flow shipped with the app. Its field mapping is refreshed on " +
						"upgrade. Duplicate it rather than editing if you want changes that survive."
				),
				"blue",
				true
			);
		}
	},

	load_compliance_checks(frm) {
		frappe.call({
			method:
				"gate_pass_management.gate_pass_management.doctype.gate_pass_source.gate_pass_source.get_compliance_check_options",
			callback({ message: checks }) {
				const grid = frm.fields_dict.compliance_rules?.grid;
				if (!grid) return;

				if (!checks || !checks.length) {
					grid.update_docfield_property("check_code", "options", "");
					frm.set_df_property(
						"compliance_rules",
						"description",
						__("No compliance providers are installed on this site.")
					);
					grid.refresh();
					return;
				}

				grid.update_docfield_property("check_code", "options", checks.map((c) => c.value).join("\n"));
				frm.set_df_property(
					"compliance_rules",
					"description",
					__("Available checks: {0}", [checks.map((c) => `${c.label} (${c.value})`).join(", ")])
				);
				grid.refresh();
			},
		});
	},
});
