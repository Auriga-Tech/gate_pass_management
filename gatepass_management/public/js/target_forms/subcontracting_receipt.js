// A receipt made from a Gate Pass is cancelled first; the Gate Pass can only be
// cancelled afterwards (Gate Pass Settings > Cancellation Policy). Without this,
// Frappe's "Cancel All Documents" dialog offers to cancel the Gate Pass before the
// receipt, which the gate pass refuses, leaving neither cancellable.
frappe.ui.form.on("Subcontracting Receipt", {
	refresh(frm) {
		frm.ignore_doctypes_on_cancel_all = Array.from(
			new Set([...(frm.ignore_doctypes_on_cancel_all || []), "Gate Pass"])
		);
	},
});
