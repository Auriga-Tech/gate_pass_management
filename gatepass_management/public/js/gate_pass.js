// Gate Pass form script.
//
// Convenience only. Every rule enforced here is enforced again on the server —
// a rule that lives only in the browser is bypassed by every API call, data
// import and bulk operation.

frappe.ui.form.on("Gate Pass", {
	setup(frm) {
		frm.set_query("gate", () => ({ filters: { is_active: 1, location: frm.doc.location || undefined } }));
		frm.set_query("location", () => ({ filters: { is_active: 1 } }));
		frm.set_query("transporter", () => ({ filters: { is_transporter: 1 } }));
		frm.set_query("discrepancy_reason", "items", () => ({ filters: { is_active: 1 } }));
	},

	refresh(frm) {
		frm.trigger("render_compliance");
		frm.trigger("add_buttons");
		frm.trigger("apply_qty_policy");
		frm.trigger("show_amended_warning");

		if (frm.doc.docstatus === 1) {
			frm.page.set_indicator(
				__(frm.doc.status),
				gatepass.STATUS_COLOURS[frm.doc.status] || "gray"
			);
		}
	},

	// The operator picks the document they are holding; direction follows from it.
	source_type(frm) {
		if (!frm.doc.source_type) return;
		frappe.db.get_value("Gate Pass Source", frm.doc.source_type, ["direction", "source_doctype", "sub_type"])
			.then(({ message }) => {
				if (!message) return;
				frm.set_value("direction", message.direction);
				frm.set_value("source_doctype", message.source_doctype);
				frm.set_value("source_sub_type", message.sub_type);
			});
	},

	direction(frm) {
		frm.trigger("add_buttons");
	},

	add_buttons(frm) {
		if (frm.doc.docstatus === 0) {
			frm.trigger("add_get_items_buttons");
		}

		if (frm.doc.docstatus === 1) {
			frm.trigger("add_create_target_button");
			frm.trigger("add_post_submit_buttons");
		}
	},

	add_get_items_buttons(frm) {
		frappe.call({
			method: "gatepass_management.api.gate_pass.list_sources",
			args: { direction: frm.doc.direction || undefined },
			callback({ message }) {
				(message || []).forEach((source) => {
					frm.add_custom_button(
						__(source.button_label),
						() => gatepass.pick_source_document(frm, source),
						__("Get Items From")
					);
				});
			},
		});
	},

	add_create_target_button(frm) {
		if (!frm.doc.source_type) return;
		frappe.db.get_value("Gate Pass Source", frm.doc.source_type,
			["target_doctype", "target_creation_mode"]
		).then(({ message }) => {
			if (!message || !message.target_doctype) return;
			if (!["Manual Button", "From Target Form"].includes(message.target_creation_mode)) return;
			if (flt(frm.doc.per_processed) >= 100) return;

			frm.add_custom_button(__("Create {0}", [__(message.target_doctype)]), () => {
				frappe.call({
					method: "gatepass_management.targets.create.create_target",
					args: { gate_pass: frm.doc.name, target_doctype: message.target_doctype },
					freeze: true,
					freeze_message: __("Creating {0}…", [__(message.target_doctype)]),
					callback({ message: result }) {
						if (!result) return;
						// Both columns always shown. A partial batch is never
						// presented as a success.
						frappe.msgprint({
							title: result.failed.length
								? __("Completed with problems")
								: __("Done"),
							message: result.message,
							indicator: result.failed.length ? "orange" : "green",
						});
						frm.reload_doc();
					},
				});
			}).addClass("btn-primary");
		});
	},

	add_post_submit_buttons(frm) {
		frm.add_custom_button(__("Amend Entry / Exit Time"),
			() => gatepass.amend_timestamp(frm), __("Correct"));

		frm.add_custom_button(__("Record Discrepancy"),
			() => gatepass.record_discrepancy(frm), __("Correct"));

		frm.add_custom_button(__("Audit Trail"), () => {
			frappe.set_route("List", "Gate Pass Event Log", { gate_pass: frm.doc.name });
		}, __("View"));
	},

	show_amended_warning(frm) {
		if (!frm.doc.timestamps_amended) return;
		frm.dashboard.add_comment(
			__("Entry or exit time was amended after submission. See the Audit Trail for what changed and why."),
			"orange", true
		);
	},

	// Locked flows: stop the operator restating an invoice. Differences are
	// recorded as shortage, damage or rejection instead.
	apply_qty_policy(frm) {
		if (!frm.doc.source_type || frm.doc.docstatus !== 0) return;
		frappe.db.get_value("Gate Pass Source", frm.doc.source_type, "qty_policy")
			.then(({ message }) => {
				const locked = message && message.qty_policy === "Locked to Source";
				frm.fields_dict.items.grid.update_docfield_property("qty", "read_only", locked ? 1 : 0);
				frm.fields_dict.items.grid.refresh();
				if (locked) {
					frm.dashboard.add_comment(
						__("Quantities are locked to the source document. Record any difference as shortage, damage or rejection."),
						"blue", true
					);
				}
			});
	},

	render_compliance(frm) {
		const wrapper = frm.fields_dict.compliance_html;
		if (!wrapper) return;
		if (!frm.doc.compliance_checks || !frm.doc.compliance_checks.length) {
			wrapper.$wrapper.empty();
			frm.toggle_display("sb_compliance", false);
			return;
		}
		frm.toggle_display("sb_compliance", true);
		gatepass.draw_compliance(frm, frm.doc.compliance_checks);
	},
});

frappe.ui.form.on("Gate Pass Item", {
	qty(frm, cdt, cdn) { gatepass.balance_row(frm, cdt, cdn); },
	shortage_qty(frm, cdt, cdn) { gatepass.balance_row(frm, cdt, cdn); },
	damaged_qty(frm, cdt, cdn) { gatepass.balance_row(frm, cdt, cdn); },
	rejected_qty(frm, cdt, cdn) { gatepass.balance_row(frm, cdt, cdn); },
	rate(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
	},
});

// Accepted qty is derived, so the operator enters what went wrong rather than
// doing the arithmetic.
gatepass.balance_row = function (frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const lost = flt(row.shortage_qty) + flt(row.damaged_qty) + flt(row.rejected_qty);
	frappe.model.set_value(cdt, cdn, "accepted_qty", Math.max(0, flt(row.qty) - lost));
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
};

gatepass.draw_compliance = function (frm, checks) {
	const rows = checks.map((c) => {
		const colour = {
			Generated: "var(--green-500)", "Not Required": "var(--blue-500)",
			"Not Applicable": "var(--gray-400)", Pending: "var(--orange-500)",
			Failed: "var(--red-500)", "Provider Unavailable": "var(--red-500)",
		}[c.status] || "var(--gray-400)";

		return `
			<div class="gp-compliance-row" data-status="${frappe.utils.escape_html(c.status)}">
				<span class="gp-compliance-dot" style="background:${colour}"></span>
				<div class="gp-compliance-body">
					<div class="gp-compliance-label">${frappe.utils.escape_html(c.label)}
						<span class="text-muted">— ${__(c.status)}</span></div>
					${c.document_no ? `<div class="gp-compliance-no">${frappe.utils.escape_html(c.document_no)}</div>` : ""}
					${c.message ? `<div class="gp-compliance-msg">${frappe.utils.escape_html(c.message)}</div>` : ""}
					${c.remediation ? `<div class="gp-compliance-fix">${frappe.utils.escape_html(c.remediation)}</div>` : ""}
				</div>
			</div>`;
	}).join("");

	frm.fields_dict.compliance_html.$wrapper.html(`
		<div class="gp-compliance">
			${rows}
			<div><button class="btn btn-xs btn-default gp-refresh-compliance">
				${__("Re-check")}</button></div>
		</div>`);

	// The operator presses this after the sales team generates the missing
	// document, while the vehicle waits at the gate.
	frm.fields_dict.compliance_html.$wrapper.find(".gp-refresh-compliance").on("click", () => {
		frappe.call({
			method: "gatepass_management.api.gate_pass.refresh_compliance",
			args: { gate_pass: frm.doc.name },
			freeze: true,
			freeze_message: __("Re-checking…"),
			callback({ message }) {
				if (!message) return;
				gatepass.draw_compliance(frm, message.checks);
				frappe.show_alert({
					message: __("Compliance: {0}", [__(message.status)]),
					indicator: message.status === "Passed" ? "green" : "orange",
				});
			},
		});
	});
};

gatepass.amend_timestamp = function (frm) {
	const is_in = frm.doc.direction === "In";
	const fieldname = is_in ? "entry_datetime" : "exit_datetime";

	frappe.prompt(
		[
			{
				fieldname: "value", fieldtype: "Datetime", reqd: 1,
				label: is_in ? __("Entry Date & Time") : __("Exit Date & Time"),
				default: frm.doc[fieldname] || frappe.datetime.now_datetime(),
			},
			{
				fieldname: "reason", fieldtype: "Small Text", reqd: 1, label: __("Reason"),
				description: __("Recorded in the audit trail against your name."),
			},
		],
		(values) => {
			frappe.call({
				method: "gatepass_management.api.gate_pass.amend_timestamp",
				args: { gate_pass: frm.doc.name, fieldname, ...values },
				freeze: true,
				callback: () => frm.reload_doc(),
			});
		},
		__("Amend Time"), __("Save")
	);
};

gatepass.record_discrepancy = function (frm) {
	const fields = [
		{
			fieldname: "rows", fieldtype: "Table", label: __("Items"),
			cannot_add_rows: true, in_place_edit: true,
			data: frm.doc.items.map((r) => ({
				name: r.name, item_code: r.item_code, qty: r.qty,
				shortage_qty: r.shortage_qty, damaged_qty: r.damaged_qty,
				rejected_qty: r.rejected_qty, discrepancy_reason: r.discrepancy_reason,
			})),
			get_data: () => fields[0].data,
			fields: [
				{ fieldname: "item_code", fieldtype: "Data", label: __("Item"), read_only: 1, in_list_view: 1, columns: 2 },
				{ fieldname: "qty", fieldtype: "Float", label: __("Qty"), read_only: 1, in_list_view: 1, columns: 1 },
				{ fieldname: "shortage_qty", fieldtype: "Float", label: __("Short"), in_list_view: 1, columns: 1 },
				{ fieldname: "damaged_qty", fieldtype: "Float", label: __("Damaged"), in_list_view: 1, columns: 1 },
				{ fieldname: "rejected_qty", fieldtype: "Float", label: __("Rejected"), in_list_view: 1, columns: 1 },
				{
					fieldname: "discrepancy_reason", fieldtype: "Link", label: __("Reason"),
					options: "Gate Pass Discrepancy Reason", in_list_view: 1, columns: 3,
				},
				{ fieldname: "name", fieldtype: "Data", hidden: 1 },
			],
		},
		{ fieldname: "notes", fieldtype: "Text", label: __("What happened"), reqd: 1 },
	];

	const dialog = new frappe.ui.Dialog({
		title: __("Record Discrepancy"),
		size: "large",
		fields,
		primary_action_label: __("Save"),
		primary_action(values) {
			const payload = {};
			(values.rows || []).forEach((r) => {
				payload[r.name] = {
					shortage_qty: flt(r.shortage_qty), damaged_qty: flt(r.damaged_qty),
					rejected_qty: flt(r.rejected_qty), discrepancy_reason: r.discrepancy_reason,
				};
			});
			frappe.call({
				method: "gatepass_management.api.gate_pass.record_discrepancy",
				args: { gate_pass: frm.doc.name, rows: JSON.stringify(payload), notes: values.notes },
				freeze: true,
				callback() { dialog.hide(); frm.reload_doc(); },
			});
		},
	});
	dialog.show();
};

gatepass.pick_source_document = function (frm, source) {
	const filters = source.source_filters ? JSON.parse(source.source_filters) : {};

	new frappe.ui.form.MultiSelectDialog({
		doctype: source.source_doctype,
		target: frm,
		setters: source.party_type && source.party_type !== "Company"
			? { [frappe.scrub(source.party_type)]: frm.doc.party || null } : {},
		date_field: "posting_date",
		get_query: () => ({ filters }),
		action(selections) {
			if (!selections || !selections.length) return;
			frappe.call({
				method: "gatepass_management.api.gate_pass.build_gate_pass",
				args: {
					source_type: source.name,
					source_name: selections[0],
					target_doc: frm.doc.docstatus === 0 && frm.doc.items.length
						? JSON.stringify(frm.doc) : null,
				},
				freeze: true,
				callback({ message }) {
					if (!message) return;
					frappe.model.sync(message);
					frm.refresh();
					cur_dialog && cur_dialog.hide();
				},
			});
		},
	});
};
