"""Rename the "Gate Pass" module to "Gate Pass Management".

The module name decides the URL prefix Frappe puts on this app's sidebar links.
"Gate Pass" gives `gate-pass`, which is also the Gate Pass DocType's route, so
links such as /desk/gate-pass/gate-pass-source resolve to a Gate Pass document
named "gate-pass-source" and show "not found".

Frappe only lets custom modules be renamed, so this creates the new Module Def,
points every Link to Module Def at it, then drops the old one. Runs before model
sync so the DocType JSON, which now names the new module, finds it waiting.
"""

import frappe

OLD = "Gate Pass"
NEW = "Gate Pass Management"
APP = "gatepass_management"


def execute():
	if not frappe.db.exists("Module Def", OLD):
		return

	if not frappe.db.exists("Module Def", NEW):
		# db_insert, not insert: Module Def's own hooks would write modules.txt.
		frappe.new_doc("Module Def").update({"module_name": NEW, "app_name": APP}).db_insert()

	for doctype, fieldname in _module_link_fields():
		frappe.db.sql(
			f"update `tab{doctype}` set `{fieldname}` = %s where `{fieldname}` = %s",  # nosemgrep
			(NEW, OLD),
		)

	# Plain-text module fields that Link-field matching cannot see.
	frappe.db.set_value("Workspace Sidebar", {"module": OLD}, "module", NEW, update_modified=False)

	frappe.db.delete("Module Def", {"name": OLD})
	frappe.clear_cache()


def _module_link_fields():
	"""(doctype, fieldname) for every field that links to Module Def, custom ones included."""
	fields = set()
	for table in ("DocField", "Custom Field"):
		column = "parent" if table == "DocField" else "dt"
		for row in frappe.get_all(
			table, filters={"fieldtype": "Link", "options": "Module Def"}, fields=[column, "fieldname"]
		):
			fields.add((row[column], row["fieldname"]))

	return sorted(
		(doctype, fieldname)
		for doctype, fieldname in fields
		if not frappe.get_meta(doctype).issingle and frappe.db.table_exists(doctype)
	)
