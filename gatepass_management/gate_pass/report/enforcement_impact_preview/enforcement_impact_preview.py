"""Enforcement Impact Preview — what would break if we tightened the rules.

This report is what turns "progressive enforcement" from a slogan into a
decision someone can actually make. It replays past gate passes against a
candidate preset and reports which rules would have blocked them, how often,
and for whom.

It is read-only. It evaluates rule *actions*, not rule *logic*: it answers
"which rules change from Warn to Block, and how much did those rules fire", by
counting the warnings already recorded in the event log. That is the honest
question — we know what fired historically because Advisory mode recorded it.

Nothing here writes. Running it changes no configuration.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, today

from gatepass_management.rules import catalogue


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, _message(filters, data), _chart(data), _summary(data)


def get_columns():
	return [
		{"label": _("Rule"), "fieldname": "rule_code", "fieldtype": "Data", "width": 180},
		{"label": _("What It Checks"), "fieldname": "rule_name", "fieldtype": "Data",
		 "width": 300},
		{"label": _("Category"), "fieldname": "category", "fieldtype": "Data", "width": 140},
		{"label": _("Now"), "fieldname": "current_action", "fieldtype": "Data", "width": 90},
		{"label": _("Would Become"), "fieldname": "new_action", "fieldtype": "Data",
		 "width": 120},
		{"label": _("Change"), "fieldname": "change", "fieldtype": "Data", "width": 130},
		{"label": _("Times Fired"), "fieldname": "times_fired", "fieldtype": "Int",
		 "width": 110},
		{"label": _("Gate Passes Affected"), "fieldname": "gate_passes", "fieldtype": "Int",
		 "width": 160},
		{"label": _("Users Affected"), "fieldname": "users", "fieldtype": "Int", "width": 130},
		{"label": _("Impact"), "fieldname": "impact", "fieldtype": "Data", "width": 120},
	]


def get_data(filters):
	days = cint(filters.get("days")) or 30
	preset = filters.get("preset") or catalogue.PRESET_BALANCED
	since = add_days(today(), -days)

	fired = _warning_counts(since)
	settings = frappe.get_cached_doc("Gate Pass Settings")
	current = {r.rule_code: r.action for r in settings.get("rules") or []}

	rows = []
	for rule in catalogue.CONFIGURABLE_RULES:
		now = current.get(rule.code) or catalogue.preset_action(
			rule, settings.get("enforcement_preset") or catalogue.PRESET_ADVISORY
		)
		would = catalogue.preset_action(rule, preset)

		stats = fired.get(rule.code, {"count": 0, "gate_passes": set(), "users": set()})

		# Only rules that get stricter matter here. A rule loosening is not a risk.
		tightening = _rank(would) > _rank(now)
		if not tightening and not stats["count"]:
			continue

		rows.append(
			{
				"rule_code": rule.code,
				"rule_name": rule.label,
				"category": rule.category,
				"current_action": now,
				"new_action": would,
				"change": _("Tightens") if tightening else _("No change"),
				"times_fired": stats["count"],
				"gate_passes": len(stats["gate_passes"]),
				"users": len(stats["users"]),
				"impact": _impact(tightening, stats["count"]),
			}
		)

	# Worst first: the rules that would block the most work.
	rows.sort(key=lambda r: (r["change"] != _("Tightens"), -r["times_fired"]))
	return rows


def _warning_counts(since) -> dict[str, dict]:
	"""How often each rule actually fired, from the event log.

	Advisory mode records every warning, which is precisely what makes this
	prediction grounded rather than theoretical.
	"""
	events = frappe.get_all(
		"Gate Pass Event Log",
		filters={
			"event": ["in", ["Rule Warned", "Validation Failed"]],
			"event_datetime": [">=", since],
			"rule_code": ["is", "set"],
		},
		fields=["rule_code", "gate_pass", "user"],
		limit_page_length=0,
	)

	out: dict[str, dict] = {}
	for e in events:
		bucket = out.setdefault(
			e.rule_code, {"count": 0, "gate_passes": set(), "users": set()}
		)
		bucket["count"] += 1
		if e.gate_pass:
			bucket["gate_passes"].add(e.gate_pass)
		if e.user:
			bucket["users"].add(e.user)
	return out


def _rank(action: str) -> int:
	return {"Ignore": 0, "Warn": 1, "Block": 2, "Hard": 3}.get(action, 0)


def _impact(tightening: bool, count: int) -> str:
	if not tightening:
		return _("None")
	if count == 0:
		return _("Safe")
	if count < 5:
		return _("Low")
	if count < 25:
		return _("Moderate")
	return _("High")


def _summary(data):
	if data is None:
		return None
	tightening = [r for r in data if r["change"] == _("Tightens")]
	blocked = sum(r["times_fired"] for r in tightening)
	return [
		{"value": len(tightening), "label": _("Rules That Tighten"), "datatype": "Int"},
		{
			"value": blocked,
			"label": _("Operations That Would Have Been Blocked"),
			"datatype": "Int",
			"indicator": "Red" if blocked else "Green",
		},
		{
			"value": len({r["rule_code"] for r in tightening if r["times_fired"] == 0}),
			"label": _("Safe To Tighten Now"),
			"datatype": "Int",
			"indicator": "Green",
		},
	]


def _message(filters, data) -> str:
	days = cint(filters.get("days")) or 30
	preset = filters.get("preset") or catalogue.PRESET_BALANCED
	tightening = [r for r in data if r["change"] == _("Tightens")]
	blocked = sum(r["times_fired"] for r in tightening)

	if not tightening:
		return _(
			"Switching to <b>{0}</b> would not tighten any rule beyond its current setting."
		).format(preset)

	if not blocked:
		return _(
			"Switching to <b>{0}</b> tightens {1} rule(s), and none of them fired in the "
			"last {2} days. This change looks safe to apply."
		).format(preset, len(tightening), days)

	return _(
		"Switching to <b>{0}</b> tightens {1} rule(s). Over the last {2} days those rules "
		"fired <b>{3}</b> time(s) — each of which would have been blocked instead of "
		"recorded. Review the high-impact rows before applying, or set just the safe "
		"rules to Block individually."
	).format(preset, len(tightening), days, blocked)


def _chart(data):
	rows = [r for r in data if r["change"] == _("Tightens") and r["times_fired"]]
	if not rows:
		return None
	rows = sorted(rows, key=lambda r: -r["times_fired"])[:10]
	return {
		"data": {
			"labels": [r["rule_code"] for r in rows],
			"datasets": [
				{"name": _("Would Have Blocked"), "values": [r["times_fired"] for r in rows]}
			],
		},
		"type": "bar",
		"colors": ["#e24c4c"],
	}
