"""Rule evaluation.

Every business rule in the app routes through `RuleContext.check()`. That single
funnel is what makes per-rule enforcement possible: the decision of whether a
violation blocks, warns, or is skipped lives here, not scattered across fifty
call sites.

Resolution order, most specific wins:

    1. Global preset          Gate Pass Settings.enforcement_preset
    2. Per-rule setting       Gate Pass Rule row
    3. Per-source override    Gate Pass Source -> Rule Overrides
    4. Bypass role            downgrades Block to Warn, never the reverse

A bypass role can only ever loosen a rule. There is deliberately no mechanism to
make a rule stricter for a particular role: that would make behaviour depend on
who is looking, which is impossible to reason about during an audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import frappe
from frappe import _

from gatepass_management.rules import catalogue
from gatepass_management.rules.catalogue import BLOCK, HARD, IGNORE, WARN
from gatepass_management.utils.logger import get_logger


@dataclass
class Violation:
	"""A rule that fired, with everything needed to explain and audit it."""

	code: str
	action: str
	message: str
	row_idx: int | None = None
	fieldname: str | None = None
	values: dict = field(default_factory=dict)
	remediation: str = ""


class RuleContext:
	"""Collects violations for one document evaluation, then raises once.

	Collecting rather than throwing on the first failure matters at the gate: a
	guard should see everything wrong with the pass in one message, not
	discover problems one reload at a time with a truck waiting.
	"""

	def __init__(self, doc, source_config=None):
		self.doc = doc
		self.source_config = source_config
		self.violations: list[Violation] = []
		self.warnings: list[Violation] = []
		self._settings = None
		self._rule_cache: dict[str, dict] = {}
		self._override_cache: dict[str, dict] | None = None
		self._roles: set[str] | None = None
		self.logger = get_logger()

	# -- configuration lookups ---------------------------------------------

	@property
	def settings(self):
		if self._settings is None:
			self._settings = frappe.get_cached_doc("Gate Pass Settings")
		return self._settings

	@property
	def user_roles(self) -> set[str]:
		if self._roles is None:
			self._roles = set(frappe.get_roles())
		return self._roles

	def _rule_row(self, code: str) -> dict:
		if not self._rule_cache:
			for row in self.settings.get("rules") or []:
				self._rule_cache[row.rule_code] = row.as_dict()
		return self._rule_cache.get(code, {})

	def _source_override(self, code: str) -> dict:
		if self._override_cache is None:
			self._override_cache = {}
			if self.source_config:
				for row in self.source_config.get("rule_overrides") or []:
					self._override_cache[row.rule_code] = row.as_dict()
		return self._override_cache.get(code, {})

	# -- resolution --------------------------------------------------------

	def resolve_action(self, code: str) -> str:
		rule = catalogue.get(code)
		if rule.is_hard:
			return HARD

		row = self._rule_row(code)
		action = row.get("action") or catalogue.preset_action(
			rule, self.settings.get("enforcement_preset") or catalogue.PRESET_ADVISORY
		)

		# Direction / gate pass type scoping on the rule row.
		if row:
			direction = row.get("applies_to_direction")
			if direction and direction != "Both" and direction != self.doc.get("direction"):
				return IGNORE
			gp_type = row.get("applies_to_gate_pass_type")
			if gp_type and gp_type != self.doc.get("gate_pass_type"):
				return IGNORE

		override = self._source_override(code)
		if override.get("action"):
			action = override["action"]

		if action == BLOCK:
			bypass = self._bypass_roles(code, row, override)
			if bypass & self.user_roles:
				action = WARN

		return action

	def _bypass_roles(self, code: str, row: dict, override: dict) -> set[str]:
		raw = override.get("bypass_roles") or row.get("bypass_roles") or []
		if isinstance(raw, str):
			return {r.strip() for r in raw.split(",") if r.strip()}
		return {r.get("role") for r in raw if r.get("role")}

	def threshold(self, code: str, fallback: float = 0.0) -> float:
		override = self._source_override(code)
		if override.get("threshold") is not None:
			return float(override["threshold"] or 0)
		row = self._rule_row(code)
		if row.get("threshold") is not None:
			return float(row["threshold"] or 0)
		rule = catalogue.get(code)
		return float(rule.default_threshold or fallback)

	def requires_reason(self, code: str) -> bool:
		override = self._source_override(code)
		if override:
			return bool(override.get("require_override_reason"))
		return bool(self._rule_row(code).get("require_override_reason"))

	def custom_message(self, code: str) -> str | None:
		return self._rule_row(code).get("custom_message") or None

	# -- the funnel --------------------------------------------------------

	def check(
		self,
		code: str,
		condition: bool,
		message: str,
		*,
		row_idx: int | None = None,
		fieldname: str | None = None,
		values: dict | None = None,
		remediation: str = "",
	) -> bool:
		"""Evaluate one rule.

		`condition` is True when the rule is VIOLATED. Returns True if the
		document should be treated as failing this rule (i.e. it blocked).
		"""
		action = self.resolve_action(code)
		if action == IGNORE:
			return False
		if not condition:
			return False

		text = self.custom_message(code) or message
		violation = Violation(
			code=code,
			action=action,
			message=text,
			row_idx=row_idx,
			fieldname=fieldname,
			values=values or {},
			remediation=remediation,
		)

		if action in (BLOCK, HARD):
			self.violations.append(violation)
			return True

		self.warnings.append(violation)
		return False

	def is_active(self, code: str) -> bool:
		"""Whether a rule will be evaluated at all — lets callers skip expensive
		queries for rules the customer has switched off."""
		return self.resolve_action(code) != IGNORE

	# -- resolution --------------------------------------------------------

	def raise_if_blocked(self):
		"""Raise once, with everything that failed."""
		self._record_warnings()
		if not self.violations:
			return

		if len(self.violations) == 1:
			v = self.violations[0]
			frappe.throw(
				self._format_one(v),
				title=_("Gate Pass Validation Failed"),
			)

		items = "".join(f"<li>{self._format_one(v)}</li>" for v in self.violations)
		frappe.throw(
			f"<ul style='margin:0;padding-left:1.1em'>{items}</ul>",
			title=_("{0} problems must be fixed").format(len(self.violations)),
		)

	def _format_one(self, v: Violation) -> str:
		prefix = _("Row {0}: ").format(v.row_idx) if v.row_idx else ""
		text = f"{prefix}{v.message}"
		if v.remediation:
			text += f"<br><span class='text-muted'>{v.remediation}</span>"
		return text

	def _record_warnings(self):
		"""Surface warnings and write them to the event log.

		A warning nobody records is a warning nobody learns from. Each one
		becomes a Gate Pass Event Log row, which is what the Gate Pass
		Exceptions report reads — that report is how a customer discovers where
		their process actually breaks, and it is the evidence they use to decide
		whether to tighten a rule.
		"""
		if not self.warnings:
			return

		from gatepass_management.gate_pass_management.doctype.gate_pass_event_log.api import log_event

		for v in self.warnings:
			self.logger.info(
				"rule_warned",
				extra={
					"rule": v.code,
					"gate_pass": self.doc.get("name"),
					"row": v.row_idx,
					"values": v.values,
				},
			)
			# The document being checked is a Gate Pass, or a target (receipt, etc.) that points
			# at one. A target's own name is not a Gate Pass, so log against the one it links to.
			is_gate_pass = self.doc.doctype == "Gate Pass"
			gate_pass = self.doc.get("name") if is_gate_pass else self.doc.get("gate_pass")
			if gate_pass and self.doc.get("name") and not self.doc.get("__islocal"):
				log_event(
					gate_pass=gate_pass,
					event="Rule Warned",
					message=v.message,
					rule_code=v.code,
					values=v.values,
					reference_doctype=None if is_gate_pass else self.doc.doctype,
					reference_name=None if is_gate_pass else self.doc.name,
				)

		body = "".join(f"<li>{self._format_one(v)}</li>" for v in self.warnings)
		frappe.msgprint(
			f"<ul style='margin:0;padding-left:1.1em'>{body}</ul>",
			title=_("Recorded, but please check"),
			indicator="orange",
		)


def blocked_codes(doc, source_config=None) -> set[str]:
	"""Which rules would block for this document, without evaluating them.

	Used by the Enforcement Impact Preview report to answer "what would happen
	if we switched to Strict" without actually switching.
	"""
	ctx = RuleContext(doc, source_config)
	return {r.code for r in catalogue.ALL_RULES if ctx.resolve_action(r.code) in (BLOCK, HARD)}
