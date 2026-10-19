"""Adds a Gate Pass connection to the ERPNext documents it relates to.

A Gate Pass points at the document it was raised for through Source Document, a dynamic link whose doctype is
in Source DocType, so the connection is counted on those two fields. Frappe hands an override only the dashboard
data, never the doctype, hence one small function per doctype below.
"""

from frappe import _


def _dashboard(doctype):
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
