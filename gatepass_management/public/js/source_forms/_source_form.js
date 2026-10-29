// Shared behaviour for every document a gate pass can be raised FROM.
//
// Each source form gets the same two buttons, driven entirely by the Gate Pass
// Source records configured for that doctype — so enabling a new flow in
// Settings makes its button appear here with no code change:
//
//   Create -> Gate Pass   shown while something is still left to pass
//   View   -> Gate Pass   shown once any pass exists against this document
//
// Nothing here enforces anything. The server decides what may be pulled and in
// what quantity; this only saves the operator from starting at a blank form.

frappe.provide("gatepass.source");

gatepass.source.setup = function (doctype) {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			if (frm.doc.docstatus !== 1) return;
			gatepass.source.add_buttons(frm, doctype);
		},
	});
};

gatepass.source.add_buttons = function (frm, doctype) {
	frappe.call({
		method: "gatepass_management.api.gate_pass.list_sources",
		args: { source_doctype: doctype },
		callback({ message: flows }) {
			if (!flows || !flows.length) return;
			gatepass.source.add_create_button(frm, flows);
			gatepass.source.add_view_button(frm);
		},
	});
};

gatepass.source.add_create_button = function (frm, flows) {
	// Only offer to create when something is actually left to pass. Asking the
	// server for the pending quantity keeps the single source of truth on the
	// server — the ledger — rather than guessing from the document's own fields.
	frappe.call({
		method: "gatepass_management.api.gate_pass.get_pending",
		args: {
			source_doctype: frm.doctype,
			source_name: frm.doc.name,
			source_type: flows[0].name,
		},
		callback({ message: pending }) {
			const anything_left = Object.values(pending || {}).some((row) => flt(row.pending) > 0);
			if (!anything_left) return;

			flows.forEach((flow) => {
				frm.add_custom_button(
					gatepass.source.label(flow, flows.length),
					() => gatepass.source.create(frm, flow),
					__("Create")
				);
			});
		},
	});
};

// A flow's Button Label reads from inside the Gate Pass form — "Get Items From
// -> Purchase Order". Reused here it says "Create -> Purchase Order" on a
// Purchase Order, which is nonsense. Name the thing being created instead, and
// only qualify it when one document has several flows to choose between, as a
// Subcontracting Order does.
gatepass.source.label = function (flow, count) {
	if (count < 2) return __("Gate Pass");
	const qualifier = flow.sub_type || flow.direction;
	return __("Gate Pass ({0})", [__(qualifier)]);
};

gatepass.source.create = function (frm, flow) {
	frappe.call({
		method: "gatepass_management.api.gate_pass.build_gate_pass",
		args: { source_type: flow.name, source_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Building Gate Pass…"),
		callback({ message: doc }) {
			if (!doc) return;
			frappe.model.sync(doc);
			frappe.set_route("Form", "Gate Pass", doc.name);
		},
	});
};

gatepass.source.add_view_button = function (frm) {
	frappe.call({
		method: "gatepass_management.utils.dashboards.get_gate_pass_names",
		args: { doctype: frm.doctype, name: frm.doc.name },
		callback({ message: names }) {
			if (!names || !names.length) return;
			frm.add_custom_button(
				__("Gate Pass"),
				() => {
					if (names.length === 1) {
						frappe.set_route("Form", "Gate Pass", names[0]);
					} else {
						frappe.set_route("List", "Gate Pass", { name: ["in", names] });
					}
				},
				__("View")
			);
		},
	});
};
