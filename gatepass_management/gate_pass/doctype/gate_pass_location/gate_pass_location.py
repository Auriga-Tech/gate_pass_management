# Copyright (c) 2026, Auriga IT and contributors
# For license information, please see license.txt

from frappe.utils.nestedset import NestedSet


class GatePassLocation(NestedSet):
	nsm_parent_field = "parent_gate_pass_location"
