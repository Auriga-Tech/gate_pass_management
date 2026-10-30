"""Insert-only audit record."""

import frappe
from frappe import _
from frappe.model.document import Document


class GatePassEventLog(Document):
	def validate(self):
		# Belt and braces: permissions already deny write, but a programmatic
		# save through ignore_permissions would otherwise slip past.
		if not self.is_new():
			frappe.throw(_("Gate Pass Event Log entries cannot be modified."))

	def on_trash(self):
		frappe.throw(
			_("Gate Pass Event Log entries cannot be deleted. Set a retention period in "
			  "Gate Pass Settings if you need them removed on a schedule.")
		)
