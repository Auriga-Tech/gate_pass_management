// Shared behaviour for every document a gate pass PRODUCES.
//
// Two jobs:
//
//   Get Items From -> Gate Pass   pull a submitted pass into this receipt
//   a notice when the flow requires a gate pass and none is linked yet
//
// The server is what actually enforces the requirement (targets.guards), so a
// receipt created by API or data import is checked the same way. This only
// makes the rule visible to someone typing, before they waste the work.

frappe.provide("gatepass.target");

gatepass.target.setup = function (doctype) {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			if (frm.doc.docstatus !== 0) return;
			gatepass.target.add_pull_button(frm);
			gatepass.target.show_requirement(frm);
		},
	});
};

gatepass.target.add_pull_button = function (frm) {
	if (!frm.meta.fields.some((f) => f.fieldname === "gate_pass")) return;

	frm.add_custom_button(
		__("Gate Pass"),
		() => gatepass.target.pick(frm),
		__("Get Items From")
	);
};

gatepass.target.pick = function (frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Select Gate Pass"),
		fields: [
			{
				fieldname: "gate_pass",
				fieldtype: "Link",
				label: __("Gate Pass"),
				options: "Gate Pass",
				reqd: 1,
				get_query: () => ({
					query: "gate_pass_management.api.gate_pass.gate_pass_query",
					filters: { target_doctype: frm.doctype, party: frm.doc.supplier || frm.doc.customer },
				}),
			},
		],
		primary_action_label: __("Get Items"),
		primary_action({ gate_pass }) {
			dialog.hide();
			frappe.call({
				method: "gate_pass_management.targets.create.create_target",
				args: { gate_pass, target_doctype: frm.doctype },
				freeze: true,
				freeze_message: __("Creating {0}…", [__(frm.doctype)]),
				callback({ message: result }) {
					if (!result) return;
					frappe.msgprint({
						title: result.failed.length ? __("Completed with problems") : __("Done"),
						message: result.message,
						indicator: result.failed.length ? "orange" : "green",
					});
					if (result.created && result.created.length) {
						frappe.set_route("Form", frm.doctype, result.created[0]);
					}
				},
			});
		},
	});
	dialog.show();
};

// Say so up front when this flow requires a gate pass, rather than letting the
// operator fill in a whole receipt and be refused at submit.
gatepass.target.show_requirement = function (frm) {
	if (frm.doc.gate_pass) return;

	frappe.call({
		method: "gate_pass_management.api.gate_pass.target_requirement",
		args: { target_doctype: frm.doctype },
		callback({ message }) {
			if (!message || message.requirement === "Not Required") return;
			const text =
				message.requirement === "Required"
					? __("A Gate Pass is required for this {0}. Use Get Items From → Gate Pass.", [
							__(frm.doctype),
					  ])
					: __("This {0} may only be created from a Gate Pass.", [__(frm.doctype)]);
			frm.dashboard.add_comment(text, message.blocking ? "red" : "orange", true);
		},
	});
};
