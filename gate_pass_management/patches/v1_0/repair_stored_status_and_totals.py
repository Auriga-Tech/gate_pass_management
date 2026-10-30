"""Repair what two lifecycle bugs left in the database.

Until now a cancelled Gate Pass kept the status it had when it was cancelled
(for example "Inside"), and a change made after submission, such as a discrepancy
recorded at unloading, never reached the stored totals or `has_discrepancy`. The
code now stores both; this puts right the passes written before that.
"""

import frappe
from frappe.utils import flt


def execute():
	frappe.db.sql(
		"""
		update `tabGate Pass` set status = 'Cancelled'
		where docstatus = 2 and ifnull(status, '') != 'Cancelled'
		"""
	)

	for name in frappe.get_all("Gate Pass", filters={"docstatus": 1}, pluck="name"):
		doc = frappe.get_doc("Gate Pass", name)
		computed = doc._derived_totals()
		changed = {
			f: computed[f]
			for f in _TOTALS
			if flt(computed[f]) != flt(doc.get(f)) and f not in ("processed_qty", "per_processed")
		}
		if changed:
			frappe.db.set_value("Gate Pass", name, changed, update_modified=False)


# Totals that depend only on the rows. The processed figures come from target
# documents and are kept current by target creation, so they are left alone.
_TOTALS = (
	"total_qty", "total_accepted_qty", "total_shortage_qty", "total_damaged_qty",
	"total_rejected_qty", "total_amount", "total_packages", "total_charges",
	"has_discrepancy", "processed_qty", "per_processed",
)
