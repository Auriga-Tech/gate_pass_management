"""Rename the "Gate Pass" module to "Gate Pass Management".

The module name decides the URL prefix Frappe puts on this app's sidebar links.
"Gate Pass" gives `gate-pass`, which is also the Gate Pass DocType's route, so
links such as /desk/gate-pass/gate-pass-source resolve to a Gate Pass document
named "gate-pass-source" and show "not found".

Frappe only lets custom modules be renamed, so this creates the new Module Def,
points every Link to Module Def at it, then drops the old one. Runs before model
sync so the DocType JSON, which now names the new module, finds it waiting.

Idempotent: it returns immediately once the old Module Def is gone.
"""

import frappe

OLD = "Gate Pass"
NEW = "Gate Pass Management"
APP = "gate_pass_management"

# Module is stored as plain text here, so a Link-field sweep cannot see it.
TEXT_MODULE_FIELDS = (("Workspace Sidebar", "module"),)


def execute():
	if not frappe.db.exists("Module Def", OLD):
		return

	if not frappe.db.exists("Module Def", NEW):
		# db_insert, not insert: Module Def's own hooks would rewrite modules.txt.
		frappe.new_doc("Module Def").update({"module_name": NEW, "app_name": APP}).db_insert()

	for doctype, fieldname in _module_link_fields():
		_rename(doctype, fieldname)

	for doctype, fieldname in TEXT_MODULE_FIELDS:
		# These DocTypes come and go between Frappe versions; a missing one is not
		# a reason to abort a migration half way through.
		if not frappe.db.exists("DocType", doctype) or not frappe.db.table_exists(doctype):
			continue
		_rename(doctype, fieldname)

	frappe.db.delete("Module Def", {"name": OLD})
	frappe.clear_cache()


def _rename(doctype: str, fieldname: str):
	table = frappe.qb.DocType(doctype)
	frappe.qb.update(table).set(table[fieldname], NEW).where(table[fieldname] == OLD).run()


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
		if frappe.db.exists("DocType", doctype)
		and not frappe.get_meta(doctype).issingle
		and frappe.db.table_exists(doctype)
	)
