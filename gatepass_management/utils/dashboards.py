"""Adds a Gate Pass connection to the ERPNext documents it relates to.

A Gate Pass points back at the document it was raised for through Source
Document, a Dynamic Link whose doctype sits in Source DocType. The connection is
therefore counted on that pair, not on a `gate_pass` column — Gate Pass has no
such field, and asking for one made `get_open_count` fail with
"Unknown column 'gate_pass'" on every form below.

Frappe hands a dashboard override only the dashboard data, never the doctype it
is building for, so the Dynamic Link needs one small function per doctype.

A document can relate to a Gate Pass two ways round, and only one of them is a
field on Gate Pass:

  * as the SOURCE — the pass was raised from it; Gate Pass.source_document
    points here, so Frappe can count it.
  * as the TARGET — the pass produced it; the link lives on the target itself
    (`<target>.gate_pass`) and in the pass's references table, neither of which
    Frappe's connection count can follow backwards.

Rather than lose the second kind, the target-side passes are added to the same
connection through `internal_links`-style preloading in `get_gate_pass_names`,
which the form script uses to show them alongside.
"""

import frappe
from frappe import _

# Documents that can be the source of a gate pass, the target of one, or both.
RELATED_DOCTYPES = (
	"Purchase Order",
	"Subcontracting Order",
	"Purchase Receipt",
	"Subcontracting Receipt",
	"Stock Entry",
	"Delivery Note",
	"Sales Invoice",
)


def _dashboard(doctype: str):
	def get_dashboard_data(data=None):
		data = data or {}
		data.setdefault("transactions", [])
		data.setdefault("non_standard_fieldnames", {})
		data.setdefault("dynamic_links", {})

		data["non_standard_fieldnames"]["Gate Pass"] = "source_document"
		data["dynamic_links"]["source_document"] = [doctype, "source_doctype"]

		data["transactions"].append({"label": _("Gate"), "items": ["Gate Pass"]})
		return data

	return get_dashboard_data


get_purchase_order_dashboard = _dashboard("Purchase Order")
get_subcontracting_order_dashboard = _dashboard("Subcontracting Order")
get_purchase_receipt_dashboard = _dashboard("Purchase Receipt")
get_subcontracting_receipt_dashboard = _dashboard("Subcontracting Receipt")
get_stock_entry_dashboard = _dashboard("Stock Entry")
get_delivery_note_dashboard = _dashboard("Delivery Note")
get_sales_invoice_dashboard = _dashboard("Sales Invoice")


@frappe.whitelist()
def get_gate_pass_names(doctype: str, name: str) -> list[str]:
	"""Every Gate Pass related to this document, both directions.

	The dashboard count only sees passes this document was the source of. A
	receipt created FROM a gate pass links the other way, so it would otherwise
	show no connection at all on the very document the pass produced.
	"""
	frappe.has_permission(doctype, "read", name, throw=True)

	names = set(
		frappe.get_all(
			"Gate Pass",
			filters={"source_doctype": doctype, "source_document": name, "docstatus": ["<", 2]},
			pluck="name",
		)
	)

	if frappe.get_meta(doctype).has_field("gate_pass"):
		linked = frappe.db.get_value(doctype, name, "gate_pass")
		if linked:
			names.add(linked)

	names.update(
		frappe.get_all(
			"Gate Pass Reference",
			filters={"reference_doctype": doctype, "reference_name": name},
			pluck="parent",
		)
	)

	return sorted(names)
