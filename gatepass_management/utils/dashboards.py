"""Adds a Gate Pass connection to the ERPNext documents it relates to."""

from frappe import _


def get_dashboard_data(data=None):
	data = data or {}
	data.setdefault("transactions", [])
	data.setdefault("non_standard_fieldnames", {})

	# Our link field is `gate_pass` on every target. Several base dashboards
	# assume the doctype's snake-case name instead, which silently breaks the
	# batched connection-count query — so state it explicitly.
	data["non_standard_fieldnames"]["Gate Pass"] = "gate_pass"

	data["transactions"].append({"label": _("Gate"), "items": ["Gate Pass"]})
	return data
