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

		// Party Type is limited to the types Gate Pass Settings allows, and the
		// address and contact offered are the ones that belong to the chosen party.
		frm.set_query("party_type", () => ({
			filters: { name: ["in", (gatepass.party_config || {}).allowed || ["Customer", "Supplier"]] },
		}));
		frm.set_query("address", () => ({
			query: "frappe.contacts.doctype.address.address.address_query",
			filters: { link_doctype: frm.doc.party_type, link_name: frm.doc.party },
		}));
		frm.set_query("contact_person", () => ({
			query: "frappe.contacts.doctype.contact.contact.contact_query",
			filters: { link_doctype: frm.doc.party_type, link_name: frm.doc.party },
		}));
	},

	onload(frm) {
		gatepass.load_party_config().then(() => frm.trigger("default_party_type"));
	},

	default_party_type(frm) {
		// Only before a party is chosen, and never when a source document decides it.
		if (frm.doc.docstatus !== 0 || frm.doc.party || frm.doc.source_type) return;
		const cfg = gatepass.party_config || {};
		const type = (cfg.by_direction || {})[frm.doc.direction] || cfg.default;
		if (type && type !== frm.doc.party_type) frm.set_value("party_type", type);
	},

	direction(frm) {
		frm.trigger("default_party_type");
	},

	party_type(frm) {
		// A party belongs to one doctype; keep nothing from the previous choice.
		if (frm.doc.party) frm.set_value("party", null);
	},

	party(frm) {
		["address", "contact_person", "contact_mobile"].forEach((f) => {
			if (frm.doc[f]) frm.set_value(f, null);
		});
		if (!frm.doc.party || !frm.doc.party_type) return;
		frappe.call({
			method: "gatepass_management.api.gate_pass.get_party_defaults",
			args: { party_type: frm.doc.party_type, party: frm.doc.party },
			callback: ({ message }) => {
				if (!message) return;
				["address", "contact_person", "contact_mobile"].forEach((f) => {
					if (message[f]) frm.set_value(f, message[f]);
				});
			},
		});
	},

	refresh(frm) {
		frm._gp_qty_locked = false;
		frm.trigger("render_source_card");
		frm.trigger("render_compliance");
		frm.trigger("add_override_button");
		frm.trigger("add_buttons");
		frm.trigger("apply_qty_policy");
		frm.trigger("lock_item_rows");
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
			// Every flow, both directions: the guard picks the document in hand and the
			// direction follows from it, so filtering by the default "In" would hide
			// every dispatch flow.
			args: {},
			callback({ message }) {
				const sources = message || [];
				if (!sources.length) return;
				const label = __("Get Items From");
				frm.add_custom_button(label, () => gatepass.open_source_picker(frm, sources));
				frm.change_custom_button_type(label, null, "primary");
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

	// The Items grid offers no Add Row / Add Multiple on a draft unless "Allow Add Row"
	// is ticked in Gate Pass Settings; items are meant to come from the source documents.
	lock_item_rows(frm) {
		const grid = frm.fields_dict.items && frm.fields_dict.items.grid;
		if (!grid) return;
		// No Add Row on any draft, new or saved, unless Gate Pass Settings allows it.
		// Items then come only from Get Items From.
		const apply = () => {
			const allow = !!(gatepass.party_config || {}).allow_add_item_rows;
			grid.cannot_add_rows = frm.doc.docstatus === 0 && !allow;
			grid.refresh();
		};
		apply();
		// Read the setting fresh, so a change in Gate Pass Settings shows on the next refresh.
		frappe.xcall("gatepass_management.api.gate_pass.get_party_config").then((cfg) => {
			gatepass.party_config = cfg;
			apply();
		});
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
				frm._gp_qty_locked = !!locked;
				frm.trigger("render_notices");
			});
	},

	// One notice area, built from every note that applies, so they never overwrite or
	// repeat each other across refreshes.
	render_notices(frm) {
		const notes = [];
		if (frm.doc.compliance_override_by) {
			notes.push(__("Compliance overridden by {0}: {1}", [
				frappe.user.full_name(frm.doc.compliance_override_by),
				frappe.utils.escape_html(frm.doc.compliance_override_reason || ""),
			]));
		}
		if (frm._gp_qty_locked && frm.doc.docstatus === 0) {
			notes.push(__("Quantities are locked to the source document. Record any difference as shortage, damage or rejection."));
		}
		frm.set_intro("");
		if (notes.length) {
			frm.set_intro(notes.join("<br>"), frm.doc.compliance_override_by ? "orange" : "blue");
		}
	},

	add_override_button(frm) {
		frm.trigger("render_notices");
		if (frm.doc.compliance_override_by) return;
		if (frm.doc.docstatus !== 0 || frm.is_new()) return;
		if (!["Pending", "Failed"].includes(frm.doc.compliance_status)) return;

		frappe.call({
			method: "gatepass_management.api.gate_pass.can_override_compliance",
			callback({ message }) {
				if (!message) return;
				frm.add_custom_button(__("Override Compliance"), () => gatepass.override_compliance(frm));
			},
		});
	},

	render_source_card(frm) {
		const wrapper = frm.fields_dict.source_card;
		if (!wrapper) return;
		if (!frm.doc.source_document) {
			wrapper.$wrapper.empty();
			return;
		}
		gatepass.draw_source_card(frm);
	},

	// Compliance sits on its own tab, so a blocking check is flagged at the top of every tab.
	compliance_banner(frm) {
		frm.dashboard.clear_headline();
		const blocked = ["Pending", "Failed"].includes(frm.doc.compliance_status);
		if (frm.doc.docstatus !== 0 || frm.is_new() || !blocked || frm.doc.compliance_override_by) return;
		frm.dashboard.set_headline_alert(
			`${__("Statutory compliance")}: <b>${__(frm.doc.compliance_status)}</b> — ${__(
				"this pass cannot be submitted until it is resolved. See the Checks & Documents tab."
			)}`,
			"red"
		);
	},

	render_compliance(frm) {
		frm.trigger("compliance_banner");
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
	// Shortage is not editable; it is whatever is left once accepted, damaged and rejected are set.
	accepted_qty(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const shortage = Math.max(0, flt(row.qty) - flt(row.accepted_qty) - flt(row.damaged_qty) - flt(row.rejected_qty));
		if (flt(row.shortage_qty) !== shortage) frappe.model.set_value(cdt, cdn, "shortage_qty", shortage);
	},
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

// Everything here is fetched from the source document, so it is shown as a
// read-only summary rather than as a column of greyed-out inputs.
gatepass.draw_source_card = function (frm) {
	const d = frm.doc;
	const esc = frappe.utils.escape_html;
	const slug = frappe.router.slug(d.source_doctype || "");
	const cell = (label, value) => value
		? `<div class="gp-src-cell"><div class="gp-src-label">${esc(label)}</div>
			<div class="gp-src-value">${value}</div></div>` : "";

	// One link per distinct document on the pass, in the order they were added.
	const docs = [...new Set((d.items || []).map((r) => r.source_document).filter(Boolean))];
	if (!docs.length && d.source_document) docs.push(d.source_document);
	const multi = docs.length > 1;
	// A draft can drop a document again; a submitted pass cannot.
	const removable = d.docstatus === 0;
	const doc_link = `<div class="gp-src-docs">${docs.map((n) =>
		`<span class="gp-src-doc"><a href="/desk/${slug}/${encodeURIComponent(n)}">${esc(n)}</a>${removable
			? `<button type="button" class="gp-src-x" data-doc="${esc(n)}"
				title="${esc(__("Remove this document from the gate pass"))}"
				aria-label="${esc(__("Remove {0}", [n]))}">&times;</button>` : ""}</span>`).join("")}</div>`;
	const tracking = d.tracking_id
		? `<span class="gp-src-mono">${esc(d.tracking_id)}</span>` : "";

	frm.fields_dict.source_card.$wrapper.html(`
		<div class="gp-src">
			<div class="gp-src-head">
				<span class="gp-src-badge" data-dir="${esc(d.direction || "")}">
					${d.direction === "Out" ? __("Outward") : __("Inward")}</span>
				<span class="gp-src-flow">${esc(__(d.source_type || ""))}</span>
				${multi ? `<span class="gp-src-pill">${__("Spans multiple documents")}</span>` : ""}
				<span class="gp-src-lock text-muted">${__("Fetched from source · read only")}</span>
			</div>
			<div class="gp-src-grid">
				${cell(multi ? __("{0} documents", [docs.length]) + " · " + __(d.source_doctype || "Document")
					: __(d.source_doctype || "Document"), doc_link)}
				${multi ? "" : cell(__("Document Date"), d.source_document_date ? frappe.datetime.str_to_user(d.source_document_date) : "")}
				${cell(__("Sub Type"), esc(d.source_sub_type || ""))}
				${cell(__("Tracking ID"), tracking)}
			</div>
		</div>`);

	frm.fields_dict.source_card.$wrapper.find(".gp-src-x").on("click", (e) => {
		gatepass.unlink_source(frm, $(e.currentTarget).data("doc"));
	});
};

// Take one source document, and every item row that came from it, off a draft pass.
gatepass.unlink_source = function (frm, source_document) {
	if (frm.doc.docstatus !== 0) return;
	const rows = (frm.doc.items || []).filter((r) => r.source_document === source_document);
	frappe.confirm(
		__("Remove {0} and its {1} item row(s) from this gate pass?", [source_document, rows.length]),
		() => {
			rows.forEach((r) => frappe.model.clear_doc(r.doctype, r.name));
			(frm.doc.items || []).forEach((r, i) => (r.idx = i + 1));

			const left = [...new Set((frm.doc.items || []).map((r) => r.source_document).filter(Boolean))];
			frm.doc.source_document = left[0] || null;
			frm.doc.is_multi_source = left.length > 1 ? 1 : 0;
			if (!left.length) frm.doc.source_document_date = null;

			frm.refresh_field("items");
			frm.refresh_field("source_document");
			frm.trigger("render_source_card");
			frm.trigger("lock_item_rows");
			frm.dirty();
			frappe.show_alert({ message: __("{0} removed. Save to keep the change.", [source_document]), indicator: "orange" });
		}
	);
};

// Server messages carry a little HTML (a bolded name). DOMParser builds an inert
// document, so reading its text neither runs scripts nor loads anything.
gatepass.plain_text = function (html) {
	return new DOMParser().parseFromString(html || "", "text/html").body.textContent;
};

gatepass.override_compliance = function (frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Override Compliance"),
		fields: [
			{
				fieldtype: "HTML",
				options: `<p class="text-muted">${__(
					"This releases the vehicle without the statutory document. Your name and reason are recorded permanently and appear in the Compliance Exceptions report."
				)}</p>`,
			},
			{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
		],
		primary_action_label: __("Override"),
		primary_action({ reason }) {
			frappe.call({
				method: "gatepass_management.api.gate_pass.override_compliance",
				args: { gate_pass: frm.doc.name, reason },
				freeze: true,
				callback() {
					dialog.hide();
					frm.reload_doc();
				},
			});
		},
	});
	dialog.show();
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
					${c.remediation ? `<div class="gp-compliance-fix">${frappe.utils.escape_html(gatepass.plain_text(c.remediation))}</div>` : ""}
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

// One picker instead of a dropdown of a dozen near-identical names: flows are grouped
// by what is physically happening at the gate, each says when to use it, and the
// list can be searched.
gatepass.open_source_picker = function (frm, sources) {
	const esc = frappe.utils.escape_html;
	const groups = [
		{ direction: "In", title: __("Material coming in"), icon: "arrow-down-left" },
		{ direction: "Out", title: __("Material going out"), icon: "arrow-up-right" },
	];

	const dialog = new frappe.ui.Dialog({
		title: __("Get Items From"),
		size: "large",
		fields: [
			{ fieldname: "search", fieldtype: "Data", placeholder: __("Search by document, e.g. Delivery Note"), },
			{ fieldname: "list", fieldtype: "HTML" },
		],
	});

	dialog.$wrapper.addClass("gp-picker-dialog");
	// A new dialog is built each time; drop the old one from the page once it closes.
	dialog.$wrapper.on("hidden.bs.modal", () => dialog.$wrapper.remove());

	const render = (term) => {
		const t = (term || "").trim().toLowerCase();
		const html = groups.map((g) => {
			const rows = sources
				.filter((s) => s.direction === g.direction)
				.filter((s) => !t || `${s.button_label} ${s.description || ""}`.toLowerCase().includes(t))
				.map((s) => `
					<button type="button" class="gp-pick-item" data-source="${esc(s.name)}">
						<span class="gp-pick-text">
							<span class="gp-pick-name">${esc(__(s.button_label))}</span>
							${s.description ? `<span class="gp-pick-desc">${esc(s.description)}</span>` : ""}
						</span>
						<span class="gp-pick-go">${frappe.utils.icon("right", "sm")}</span>
					</button>`).join("");
			return rows ? `
				<div class="gp-pick-group" data-dir="${g.direction}">
					<div class="gp-pick-title"><span class="gp-pick-dot"></span>${esc(g.title)}</div>
					${rows}
				</div>` : "";
		}).join("");
		dialog.fields_dict.list.$wrapper.html(
			`<div class="gp-pick">${html || `<div class="gp-pick-empty text-muted">${__("No matching flow")}</div>`}</div>`
		);
	};

	render("");
	dialog.fields_dict.search.$input.on("input", (e) => render(e.target.value));
	dialog.fields_dict.list.$wrapper.on("click", ".gp-pick-item", (e) => {
		const source = sources.find((s) => s.name === $(e.currentTarget).data("source"));
		dialog.hide();
		if (source) gatepass.pick_source_document(frm, source);
	});
	dialog.show();
	dialog.fields_dict.search.$input.trigger("focus");
};

gatepass.load_party_config = function () {
	if (gatepass.party_config) return Promise.resolve(gatepass.party_config);
	return frappe
		.xcall("gatepass_management.api.gate_pass.get_party_config")
		.then((cfg) => (gatepass.party_config = cfg));
};

gatepass.pick_source_document = function (frm, source) {
	const filters = source.source_filters ? JSON.parse(source.source_filters) : {};

	new frappe.ui.form.MultiSelectDialog({
		doctype: source.source_doctype,
		target: frm,
		// "Company" and "From Field" name no party field on the source document, so
		// there is nothing to filter by; only Customer and Supplier flows do.
		setters: source.party_type && !["Company", "From Field"].includes(source.party_type)
			? { [frappe.scrub(source.party_type)]: frm.doc.party || null } : {},
		date_field: "posting_date",
		get_query: () => ({ filters }),
		action(selections) {
			if (!selections || !selections.length) return;
			frappe.call({
				method: "gatepass_management.api.gate_pass.build_gate_pass",
				args: {
					source_type: source.name,
					// Every ticked document, not just the first.
					source_name: JSON.stringify(selections),
					target_doc: frm.doc.docstatus === 0 && frm.doc.items.length
						? JSON.stringify(frm.doc) : null,
				},
				freeze: true,
				callback({ message }) {
					if (!message) return;
					cur_dialog && cur_dialog.hide();
					frappe.model.sync(message);
					// The server returns a new mapped document unless it was handed this
					// one back; refreshing the form we are on would leave it blank.
					if (message.name === frm.doc.name) {
						frm.refresh();
					} else {
						frappe.set_route("Form", message.doctype, message.name);
					}
				},
			});
		},
	});
};

// A setting changed in another browser tab (for example Allow Add Row in Gate Pass
// Settings) is picked up by an open gate pass as soon as you come back to it, instead
// of only at the next reload.
if (!gatepass._focus_bound) {
	gatepass._focus_bound = true;
	const recheck = () => {
		if (document.visibilityState === "hidden") return;
		const frm = window.cur_frm;
		if (frm && frm.doctype === "Gate Pass" && frm.fields_dict && frm.fields_dict.items) {
			frm.trigger("lock_item_rows");
		}
	};
	document.addEventListener("visibilitychange", recheck);
	window.addEventListener("focus", recheck);
}
