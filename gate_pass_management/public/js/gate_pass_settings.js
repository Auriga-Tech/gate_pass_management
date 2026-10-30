// Gate Pass Settings.
//
// The preset selector is the point of this file. Picking a preset has to rewrite
// every rule row, and without a client script the field was just a label — you
// could move it from Advisory to Strict, save, and nothing changed.

frappe.ui.form.on("Gate Pass Settings", {
	refresh(frm) {
		frm.trigger("show_rule_summary");

		frm.add_custom_button(__("Enforcement Impact Preview"), () => {
			frappe.set_route("query-report", "Enforcement Impact Preview");
		});
	},

	// Changing the preset rewrites the rule table, so confirm first — on a tuned
	// install this throws away deliberate per-rule decisions.
	enforcement_preset(frm) {
		const preset = frm.doc.enforcement_preset;
		if (!preset || preset === "Custom" || frm.is_new()) return;
		if (frm._gp_applying) return;

		frappe.confirm(
			__(
				"Set every configurable rule to the <b>{0}</b> preset?<br><br>" +
					"This replaces the action on each rule below. Statutory compliance rules " +
					"stay at Block whichever preset you choose.",
				[preset]
			),
			() => {
				frm._gp_applying = true;
				frappe
					.call({
						method: "gate_pass_management.setup.install.apply_preset",
						args: { preset },
						freeze: true,
						freeze_message: __("Applying {0}…", [preset]),
					})
					.then(() => frm.reload_doc())
					.always(() => {
						frm._gp_applying = false;
					});
			},
			() => {
				// Declined: put the field back rather than leaving it showing a
				// preset the rules do not match.
				frm._gp_applying = true;
				frm.set_value("enforcement_preset", frm.doc.__onload?.preset_before || "Custom").then(
					() => {
						frm._gp_applying = false;
					}
				);
			}
		);
	},

	// Editing any rule by hand means the rules no longer match a named preset.
	rules(frm) {
		if (frm.doc.enforcement_preset !== "Custom") {
			frm.set_value("enforcement_preset", "Custom");
		}
	},

	show_rule_summary(frm) {
		if (frm.is_new()) return;
		frappe.call({
			method: "gate_pass_management.gate_pass_management.doctype.gate_pass_settings.gate_pass_settings.get_rule_summary",
			callback({ message: counts }) {
				if (!counts) return;
				const chip = (label, n, colour) =>
					`<span class="indicator-pill ${colour}" style="margin-right:6px">${n} ${__(label)}</span>`;
				frm.dashboard.clear_headline();
				frm.dashboard.set_headline(
					chip("Block", counts.Block, "red") +
						chip("Warn", counts.Warn, "orange") +
						chip("Ignore", counts.Ignore, "gray") +
						chip("always block", counts.Hard, "blue")
				);
			},
		});
	},
});

frappe.ui.form.on("Gate Pass Rule", {
	action(frm) {
		frm.trigger("rules");
		frm.trigger("show_rule_summary");
	},
});
