"""The rule catalogue.

Every business rule in the app is declared here, once, with a stable code. This
module is the single source of truth for:

  * what rules exist
  * what each one defaults to
  * whether it may be switched off, or overridden per source
  * what the four enforcement presets do to it

`Gate Pass Settings` seeds and reconciles its child table from this catalogue on
every migrate, so adding a rule in a future version is a one-line change here.
A customer's edits to existing rows are never overwritten.

Rule codes are permanent. Renaming one is a breaking change; add a new code and
retire the old one via a patch instead.
"""

from dataclasses import dataclass, field

from frappe import _lt

# --- Actions ---------------------------------------------------------------

BLOCK = "Block"
WARN = "Warn"
IGNORE = "Ignore"
HARD = "Hard"  # not configurable; always blocks

ACTIONS = (BLOCK, WARN, IGNORE)

# --- Presets ---------------------------------------------------------------

PRESET_ADVISORY = "Advisory"
PRESET_BALANCED = "Balanced"
PRESET_STRICT = "Strict"
PRESET_CUSTOM = "Custom"

PRESETS = (PRESET_ADVISORY, PRESET_BALANCED, PRESET_STRICT, PRESET_CUSTOM)

# --- Categories ------------------------------------------------------------

CAT_DOCUMENT = "Document"
CAT_PARTY = "Party & Source"
CAT_QUANTITY = "Quantity"
CAT_DISCREPANCY = "Discrepancy"
CAT_COMPLIANCE = "Compliance"
CAT_CHECKS = "Attachments & Checks"
CAT_LIFECYCLE = "Lifecycle"
CAT_DOWNSTREAM = "Downstream Enforcement"


@dataclass(frozen=True)
class Rule:
	code: str
	label: str
	category: str
	description: str
	default_action: str = WARN
	can_ignore: bool = True
	source_overridable: bool = False
	has_threshold: bool = False
	threshold_label: str = ""
	default_threshold: float = 0.0
	# Presets that force this rule to Block regardless of the preset's general
	# posture. Statutory rules use this: "Advisory" is a statement about our own
	# process maturity, not permission to dispatch without an E-Way Bill.
	always_block: bool = False

	@property
	def is_hard(self) -> bool:
		return self.default_action == HARD


def _r(*args, **kwargs) -> Rule:
	return Rule(*args, **kwargs)


# ---------------------------------------------------------------------------
# Document integrity — HARD. Bypassing these corrupts the ledger or produces
# documents that cannot be reasoned about, so they are not configurable.
# ---------------------------------------------------------------------------

_HARD_RULES = [
	_r("DOC-DIRECTION-LOCK", "Direction is immutable after save", CAT_DOCUMENT,
	   "Changing direction after the first save would invalidate every downstream reference.",
	   HARD, can_ignore=False),
	_r("DOC-RETURNABLE-DIR", "Returnable only on outward passes", CAT_DOCUMENT,
	   "An inward gate pass cannot be marked returnable.", HARD, can_ignore=False),
	_r("DOC-COMPANY-MATCH", "Source company matches gate pass company", CAT_DOCUMENT,
	   "Prevents cross-company material leakage.", HARD, can_ignore=False),
	_r("SRC-SUBMITTED", "Source document must be submitted", CAT_PARTY,
	   "Draft child rows can be deleted, which would orphan the consumption ledger.",
	   HARD, can_ignore=False),
	_r("ITEM-REQUIRED", "Item Code required unless non-stock", CAT_QUANTITY,
	   "", HARD, can_ignore=False),
	_r("ITEM-NAME-REQUIRED", "Item Name required for non-stock rows", CAT_QUANTITY,
	   "", HARD, can_ignore=False),
	_r("ITEM-CONVERSION", "Conversion factor must be positive", CAT_QUANTITY,
	   "A zero conversion factor causes division errors downstream.", HARD, can_ignore=False),
	_r("QTY-NEGATIVE", "Quantity cannot be negative", CAT_QUANTITY,
	   "Negative quantities corrupt the consumption ledger.", HARD, can_ignore=False),
	_r("QTY-POLICY-LOCKED", "Quantity locked to source", CAT_QUANTITY,
	   "When a flow sets Qty Policy to 'Locked to Source', the quantity cannot be edited. "
	   "Record any difference as shortage, damage, or rejection instead.",
	   HARD, can_ignore=False, source_overridable=True),
	_r("DISC-BALANCE", "Accepted + shortage + damaged + rejected must equal qty", CAT_DISCREPANCY,
	   "", HARD, can_ignore=False),
	_r("DISC-NEGATIVE", "Discrepancy quantities cannot be negative", CAT_DISCREPANCY,
	   "", HARD, can_ignore=False),
	_r("DISC-ALLOWED", "Discrepancy permitted on this flow", CAT_DISCREPANCY,
	   "Governed by 'Allow Discrepancy' on the Gate Pass Source.",
	   HARD, can_ignore=False, source_overridable=True),
	_r("DISC-POST-SUBMIT", "No discrepancy edit after a target is submitted", CAT_DISCREPANCY,
	   "Once a receipt exists, the discrepancy is history. Cancel the receipt first.",
	   HARD, can_ignore=False),
	_r("TGT-CREATE-FAIL", "Auto-created target must succeed", CAT_DOWNSTREAM,
	   "A gate pass cannot half-create its target. Failure aborts the submit.",
	   HARD, can_ignore=False),
	_r("TGT-IDEMPOTENT", "One target per gate pass per reference", CAT_DOWNSTREAM,
	   "Prevents duplicate receipts from a double-click or a retried request.",
	   HARD, can_ignore=False),
	_r("DOC-EFFECTIVE-DATE", "Gate pass on or after the effective date", CAT_DOCUMENT,
	   "Set 'Enforce From Date' in Gate Pass Settings.", HARD, can_ignore=False),
]

# ---------------------------------------------------------------------------
# Configurable rules
# ---------------------------------------------------------------------------

_DOCUMENT_RULES = [
	_r("DOC-REF-DATE-FUTURE", "Reference date not in the future", CAT_DOCUMENT,
	   "The supplier invoice or challan date cannot be later than today.", BLOCK),
	_r("DOC-BACKDATE", "Posting date within the backdate window", CAT_DOCUMENT,
	   "Limits how far back a gate pass may be dated.", WARN,
	   has_threshold=True, threshold_label=_lt("Days"), default_threshold=7),
	_r("DOC-FUTUREDATE", "Posting date not in the future", CAT_DOCUMENT,
	   "", BLOCK, has_threshold=True, threshold_label=_lt("Days"), default_threshold=0),
	_r("DOC-RETURN-DATE", "Expected return on or after the gate pass date", CAT_DOCUMENT,
	   "", BLOCK),
	_r("DOC-RETURN-WINDOW", "Expected return within the permitted window", CAT_DOCUMENT,
	   "Flags returnable passes promising an unusually distant return.", WARN,
	   source_overridable=True, has_threshold=True,
	   threshold_label=_lt("Days"), default_threshold=90),
	_r("DOC-ITEMS-REQUIRED", "At least one item row", CAT_DOCUMENT,
	   "Does not apply to Visitor or Vehicle Only passes.", BLOCK, source_overridable=True),
	_r("DOC-TRACKING-UNIQUE", "Tracking ID not already used", CAT_DOCUMENT,
	   "Applies only when 'Tracking ID Unique' is enabled.", BLOCK),
	_r("DOC-GATE-LOCATION", "Gate belongs to the selected location", CAT_DOCUMENT, "", WARN),
	_r("DOC-SECURITY-OFFICER", "Security officer recorded", CAT_DOCUMENT,
	   "The accountability field: who was on the gate.", WARN),
]

_PARTY_RULES = [
	_r("PARTY-ADDRESS", "Address required for this party type", CAT_PARTY, "", WARN,
	   source_overridable=True),
	_r("PARTY-SOURCE-MATCH", "Gate pass party matches the source document", CAT_PARTY, "",
	   BLOCK, source_overridable=True),
	_r("SRC-MIXED-DOCTYPE", "All rows from one source document type", CAT_PARTY, "",
	   BLOCK, source_overridable=True),
	_r("SRC-MIXED-PARTY", "Multi-source rows share one party", CAT_PARTY, "",
	   BLOCK, source_overridable=True),
	_r("SRC-MIXED-GROUP", "Multi-source rows share the configured grouping fields", CAT_PARTY,
	   "For example, all Purchase Orders must share the same purchase type.",
	   WARN, source_overridable=True),
	_r("SRC-STATUS", "Source document status is open for a gate pass", CAT_PARTY, "",
	   BLOCK, source_overridable=True),
	_r("SRC-NONSTOCK-MIX", "Non-stock rows on a source-backed pass", CAT_PARTY, "",
	   WARN, source_overridable=True),
]

_QUANTITY_RULES = [
	_r("QTY-ZERO", "Zero-quantity rows not allowed", CAT_QUANTITY, "",
	   BLOCK, source_overridable=True),
	_r("QTY-ROW-PENDING", "Row quantity within the pending quantity on the source line",
	   CAT_QUANTITY,
	   "Defaults to Warn: the truck is already at the gate, so record the discrepancy "
	   "rather than refusing to document what arrived.",
	   WARN, source_overridable=True, has_threshold=True,
	   threshold_label=_lt("Tolerance %"), default_threshold=0),
	_r("QTY-LEDGER", "Total gate-passed quantity within the ordered quantity", CAT_QUANTITY,
	   "Sums every submitted gate pass against the same source line. Evaluated under a "
	   "row lock so two operators cannot both pass.",
	   WARN, source_overridable=True, has_threshold=True,
	   threshold_label=_lt("Tolerance %"), default_threshold=0),
	_r("QTY-DUPLICATE-ROW", "Two rows referencing the same source line", CAT_QUANTITY, "",
	   WARN, source_overridable=True),
	_r("QTY-POLICY-TOLERANCE", "Quantity within tolerance of the source", CAT_QUANTITY,
	   "Applies when Qty Policy is 'Editable within Tolerance'.",
	   WARN, source_overridable=True, has_threshold=True,
	   threshold_label=_lt("Variance %"), default_threshold=5),
	_r("QTY-WEIGHT", "Net weight is positive", CAT_QUANTITY, "", WARN),
	_r("QTY-WEIGHT-VARIANCE", "Net weight within the expected variance", CAT_QUANTITY, "",
	   IGNORE, source_overridable=True, has_threshold=True,
	   threshold_label=_lt("Variance %"), default_threshold=10),
]

_DISCREPANCY_RULES = [
	_r("DISC-NOTES", "Notes required when a discrepancy exists", CAT_DISCREPANCY, "",
	   WARN, source_overridable=True),
	_r("DISC-REASON", "Reason required on each discrepancy row", CAT_DISCREPANCY, "",
	   WARN, source_overridable=True),
	_r("DISC-REJ-WAREHOUSE", "Rejected warehouse set when damage is recorded", CAT_DISCREPANCY,
	   "Needed so damaged quantity can be received separately on the target document.",
	   WARN, source_overridable=True),
	_r("DISC-THRESHOLD", "Discrepancy within the acceptable proportion of the consignment",
	   CAT_DISCREPANCY, "Escalates unusually large shortages or damage.",
	   WARN, source_overridable=True, has_threshold=True,
	   threshold_label=_lt("% of total qty"), default_threshold=10),
]

_COMPLIANCE_RULES = [
	_r("CMP-REQUIRED", "Required statutory documents are generated", CAT_COMPLIANCE,
	   "Blocks dispatch until every applicable compliance check reports Generated. "
	   "The gate is the last point at which non-compliance is still preventable.",
	   BLOCK, source_overridable=True, always_block=True),
	_r("CMP-STALE", "Compliance re-checked at submit", CAT_COMPLIANCE,
	   "Prevents a since-cancelled IRN from passing because it was checked ten minutes ago.",
	   BLOCK, source_overridable=True, always_block=True),
	_r("CMP-PROVIDER-DOWN", "Compliance provider reachable", CAT_COMPLIANCE,
	   "Fails closed. An app that waves dispatches through whenever an API is down "
	   "provides no control at all.",
	   BLOCK, source_overridable=True, always_block=True),
]

_CHECK_RULES = [
	_r("CHK-DOC-MANDATORY", "Mandatory checklist documents attached", CAT_CHECKS, "",
	   BLOCK, source_overridable=True),
	_r("CHK-CHARGE-MANDATORY", "Mandatory charges entered", CAT_CHECKS, "",
	   WARN, source_overridable=True),
	_r("CHK-PACKAGING", "Packaging condition recorded", CAT_CHECKS, "",
	   WARN, source_overridable=True),
	_r("CHK-DOCUMENTATION", "Documentation status recorded", CAT_CHECKS, "",
	   WARN, source_overridable=True),
	_r("CHK-VEHICLE-PHOTO", "Vehicle photo attached", CAT_CHECKS, "",
	   WARN, source_overridable=True),
	_r("CHK-BATCH-SERIAL", "Batch or serial supplied where the item requires it", CAT_CHECKS,
	   "", WARN, source_overridable=True),
]

_LIFECYCLE_RULES = [
	_r("LIFE-ATTACH-LOCK", "Attachments immutable after submit", CAT_LIFECYCLE,
	   "Users holding a role in 'Attachment Unlock Roles' may still remove one; "
	   "every removal is audited.", BLOCK),
	_r("LIFE-STALE-DRAFT", "Draft gate passes are not left unsubmitted", CAT_LIFECYCLE, "",
	   IGNORE, has_threshold=True, threshold_label=_lt("Days"), default_threshold=3),
]

_DOWNSTREAM_RULES = [
	_r("TGT-REQUIRED", "Target document carries a gate pass", CAT_DOWNSTREAM,
	   "The core adoption switch. Defaults to Warn so installing the app breaks nothing.",
	   WARN, source_overridable=True),
	_r("TGT-FORBIDDEN", "Target document must not carry a gate pass", CAT_DOWNSTREAM,
	   "For flows where a gate pass is meaningless.", BLOCK, source_overridable=True),
	_r("TGT-ROW-COVERAGE", "Every target row is covered by the gate pass", CAT_DOWNSTREAM,
	   "Fails closed: rows with no source reference are reported, not skipped.",
	   WARN, source_overridable=True),
	_r("TGT-QTY-ROW", "Target quantity within the gate-passed quantity, per source line",
	   CAT_DOWNSTREAM,
	   "Defaults to Block. Goods may pass the gate with a discrepancy recorded, but a "
	   "wrong quantity must not reach the stock ledger.",
	   BLOCK, source_overridable=True, has_threshold=True,
	   threshold_label=_lt("Tolerance %"), default_threshold=0),
	_r("TGT-QTY-TOTAL", "Target quantity within the gate pass total", CAT_DOWNSTREAM,
	   "A cheap backstop for TGT-QTY-ROW.", BLOCK, source_overridable=True,
	   has_threshold=True, threshold_label=_lt("Tolerance %"), default_threshold=0),
	_r("TGT-BLOCK-NATIVE", "Target may only be created from a gate pass", CAT_DOWNSTREAM,
	   "Enforced server-side, so API and bulk imports cannot bypass it.",
	   IGNORE, source_overridable=True),
]


ALL_RULES: tuple[Rule, ...] = tuple(
	_HARD_RULES
	+ _DOCUMENT_RULES
	+ _PARTY_RULES
	+ _QUANTITY_RULES
	+ _DISCREPANCY_RULES
	+ _COMPLIANCE_RULES
	+ _CHECK_RULES
	+ _LIFECYCLE_RULES
	+ _DOWNSTREAM_RULES
)

BY_CODE: dict[str, Rule] = {r.code: r for r in ALL_RULES}

CONFIGURABLE_RULES: tuple[Rule, ...] = tuple(r for r in ALL_RULES if not r.is_hard)

SOURCE_OVERRIDABLE_CODES: frozenset[str] = frozenset(
	r.code for r in ALL_RULES if r.source_overridable
)


def get(code: str) -> Rule:
	rule = BY_CODE.get(code)
	if not rule:
		raise KeyError(f"Unknown gate pass rule code: {code}")
	return rule


def preset_action(rule: Rule, preset: str) -> str:
	"""Resolve what a preset does to a rule.

	`always_block` rules ignore the preset entirely. Advisory means "do not
	obstruct our internal process while we learn the tool"; it does not mean
	"let trucks leave without statutory documents". Relaxing a statutory rule
	stays possible, but only as a deliberate per-rule decision on the record.
	"""
	if rule.is_hard:
		return HARD
	if rule.always_block:
		return BLOCK
	if preset == PRESET_ADVISORY:
		return IGNORE if rule.default_action == IGNORE else WARN
	if preset == PRESET_STRICT:
		return BLOCK
	# Balanced, and the fallback for Custom during seeding.
	return rule.default_action
