"""The consumption ledger.

The central mechanism of the app. Every Gate Pass Item row stores `source_row` —
the name of the source document's child row (a specific Purchase Order Item, for
instance). Consumed quantity for any source line is the sum of that column over
submitted gate passes.

    consumed(source_row) = SUM(Gate Pass Item.qty)
                           WHERE source_row = <row> AND parent.docstatus = 1

Keying on the child row rather than the item code is what makes partial gate
passes chain correctly, and what stops over-consumption on one order line being
masked by under-consumption on another line of the same item.

CONCURRENCY
-----------
Reading a sum and then writing based on it is a race. Two operators submitting
against the same purchase order line at the same moment would both read the same
consumed total, both find room, and both commit — leaving the line
over-consumed with no error raised anywhere.

`consumed_qty_for_update()` therefore takes a row lock on the *source document*
before reading. The second transaction blocks until the first commits, then
re-reads the true total and fails properly. Every write path must use that
function; the plain `consumed_qty()` is for display only and says so.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import cint, flt

from gate_pass_management.utils.logger import get_logger

# How long to wait for another transaction's lock before giving up. Bounded so a
# stuck transaction produces a clear message rather than an indefinite hang.
DEFAULT_LOCK_TIMEOUT = 30


def consumed_qty(source_rows: list[str]) -> dict[str, float]:
	"""Consumed quantity per source row. DISPLAY ONLY — not lock-safe.

	Safe for populating a form, showing pending quantities, or rendering a
	report. Never use the result to decide whether a save may proceed; use
	`consumed_qty_for_update` inside the writing transaction for that.
	"""
	if not source_rows:
		return {}

	GPI = frappe.qb.DocType("Gate Pass Item")
	GP = frappe.qb.DocType("Gate Pass")

	rows = (
		frappe.qb.from_(GPI)
		.inner_join(GP)
		.on(GP.name == GPI.parent)
		.select(GPI.source_row, Sum(GPI.qty).as_("consumed"))
		.where(GPI.source_row.isin(source_rows))
		.where(GP.docstatus == 1)
		.groupby(GPI.source_row)
	).run(as_dict=True)

	return {r.source_row: flt(r.consumed) for r in rows}


def consumed_qty_for_update(
	source_doctype: str,
	source_documents: list[str],
	source_rows: list[str],
	exclude_gate_pass: str | None = None,
) -> dict[str, float]:
	"""Consumed quantity per source row, read under a lock on the source documents.

	Call this inside the transaction that is about to write. The lock is taken on
	the source document rows, so concurrent gate passes against the *same* order
	serialise while gate passes against different orders proceed in parallel.
	"""
	if not source_rows:
		return {}

	_lock_source_documents(source_doctype, source_documents)

	GPI = frappe.qb.DocType("Gate Pass Item")
	GP = frappe.qb.DocType("Gate Pass")

	query = (
		frappe.qb.from_(GPI)
		.inner_join(GP)
		.on(GP.name == GPI.parent)
		.select(GPI.source_row, Sum(GPI.qty).as_("consumed"))
		.where(GPI.source_row.isin(source_rows))
		.where(GP.docstatus == 1)
		.groupby(GPI.source_row)
	)
	if exclude_gate_pass:
		query = query.where(GP.name != exclude_gate_pass)

	rows = query.run(as_dict=True)
	return {r.source_row: flt(r.consumed) for r in rows}


def _lock_source_documents(source_doctype: str, names: list[str]):
	"""Take a row lock on each source document.

	Ordered by name so two transactions touching the same pair of documents
	always acquire in the same sequence — otherwise A locks doc1 waiting for
	doc2 while B locks doc2 waiting for doc1, and they deadlock.
	"""
	names = sorted({n for n in names if n})
	if not names or not source_doctype:
		return

	timeout = _lock_timeout()
	try:
		source = frappe.qb.DocType(source_doctype)
		frappe.qb.from_(source).select(source.name).where(source.name.isin(names)).for_update().run()
	except frappe.QueryTimeoutError:
		frappe.throw(
			_(
				"Another user is currently creating a Gate Pass against {0} {1}. "
				"Please wait a moment and try again."
			).format(_(source_doctype), ", ".join(names)),
			title=_("Busy"),
		)
	except Exception as exc:
		# A lock failure must never be silently ignored — that would put us back
		# to the unlocked read this function exists to prevent.
		get_logger().error(
			"ledger_lock_failed",
			extra={"doctype": source_doctype, "names": names, "error": str(exc)},
		)
		frappe.throw(
			_("Could not lock {0} for update. Please retry.").format(_(source_doctype)),
			title=_("Busy"),
		)


def _lock_timeout() -> int:
	try:
		return (
			cint(frappe.get_cached_value("Gate Pass Settings", None, "ledger_lock_timeout_seconds"))
			or DEFAULT_LOCK_TIMEOUT
		)
	except Exception:
		return DEFAULT_LOCK_TIMEOUT


def pending_qty(source_doctype: str, source_name: str, source_config) -> dict[str, dict]:
	"""Pending quantity per source row, for populating a new gate pass.

	Returns {source_row: {"source_qty", "consumed", "already_received", "pending"}}.

	The four pending formulas below are the ones real flows need:

      qty - consumed                   simple draw-down
      qty - max(received, consumed)    order lines where ERPNext also tracks receipt
      abs(qty) - consumed              return documents, which carry negative qty
      qty                              no netting; every pass starts from full
	"""
	child_table = source_config.child_table
	qty_field = source_config.qty_field
	consumed_field = source_config.consumed_field
	formula = source_config.pending_formula or "qty - consumed"

	child_doctype = _child_doctype(source_doctype, child_table)
	fields = ["name", qty_field]
	if consumed_field:
		fields.append(consumed_field)

	rows = frappe.get_all(
		child_doctype,
		filters={"parent": source_name, "parenttype": source_doctype},
		fields=fields,
		order_by="idx asc",
	)
	if not rows:
		return {}

	consumed = consumed_qty([r.name for r in rows])
	result = {}

	for row in rows:
		qty = flt(row.get(qty_field))
		already = flt(consumed.get(row.name, 0))
		received = flt(row.get(consumed_field)) if consumed_field else 0.0

		result[row.name] = {
			"source_qty": qty,
			"consumed": already,
			"already_received": received,
			"pending": _pending(formula, qty, already, received),
		}

	return result


def _pending(formula: str, qty: float, consumed: float, received: float) -> float:
	if formula == "qty - max(received, consumed)":
		pending = qty - max(received, consumed)
	elif formula == "abs(qty) - consumed":
		pending = abs(qty) - consumed
	elif formula == "qty":
		pending = qty
	else:
		pending = qty - consumed
	return max(0.0, flt(pending, 6))


def documents_with_pending(source_doctype: str, names: list[str], source_config) -> set[str]:
	"""Which of these source documents still have something left to gate pass.

	The picker asks this for a whole page at once, so it is two queries for the
	lot rather than two per document.
	"""
	if not names:
		return set()

	qty_field = source_config.qty_field
	consumed_field = source_config.consumed_field
	formula = source_config.pending_formula or "qty - consumed"

	fields = ["name", "parent", qty_field]
	if consumed_field:
		fields.append(consumed_field)
	rows = frappe.get_all(
		_child_doctype(source_doctype, source_config.child_table),
		filters={"parent": ["in", names], "parenttype": source_doctype},
		fields=fields,
	)
	consumed = consumed_qty([r.name for r in rows]) if rows else {}

	open_documents = set()
	for row in rows:
		received = flt(row.get(consumed_field)) if consumed_field else 0.0
		pending = _pending(
			formula, flt(row.get(qty_field)), flt(consumed.get(row.name, 0)), received
		)
		if pending > 0:
			open_documents.add(row.parent)
	return open_documents


def _child_doctype(parent_doctype: str, fieldname: str) -> str:
	meta = frappe.get_meta(parent_doctype)
	df = meta.get_field(fieldname)
	if not df or df.fieldtype not in ("Table", "Table MultiSelect"):
		frappe.throw(
			_("{0} has no child table named {1}. Check the Gate Pass Source configuration.").format(
				_(parent_doctype), frappe.bold(fieldname)
			)
		)
	return df.options


def processed_qty(gate_pass: str) -> dict[str, float]:
	"""Quantity consumed by submitted target documents, per gate pass item row."""
	rows = frappe.get_all(
		"Gate Pass Reference",
		filters={"parent": gate_pass, "docstatus": ["<", 2]},
		fields=["reference_row", "qty"],
	)
	out: dict[str, float] = {}
	for r in rows:
		if r.reference_row:
			out[r.reference_row] = out.get(r.reference_row, 0) + flt(r.qty)
	return out
