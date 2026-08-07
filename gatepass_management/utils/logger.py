"""Structured logging.

Every log line is single-line JSON carrying a trace_id. That same trace_id
appears in the user-facing error message, in the Error Log record, and in the
Gate Pass Event Log row — so an implementer can move between all three from a
string the user read off their screen.

The prior implementations this app replaces logged almost nothing, which made
"why didn't this gate pass create a receipt?" unanswerable without a database
session. That question should be answerable from the UI.
"""

from __future__ import annotations

import json
import logging

import frappe

LOGGER_NAME = "gatepass"

LEVELS = {
	"Errors Only": logging.ERROR,
	"Standard": logging.INFO,
	"Verbose": logging.DEBUG,
}


# Attribute names LogRecord owns. Passing any of these in `extra` makes
# logging.makeRecord raise KeyError, so every field we add is nested under a
# single safe key instead of being spread across the record. Doing it this way
# means a future caller cannot accidentally pick a colliding field name —
# `created`, `module`, `name`, `process` and `message` are all plausible things
# to want to log, and all of them would blow up.
_PAYLOAD_KEY = "gp_fields"


class _JsonFormatter(logging.Formatter):
	def format(self, record: logging.LogRecord) -> str:
		payload = {
			"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
			"level": record.levelname,
			"event": record.getMessage(),
		}
		payload.update(getattr(record, _PAYLOAD_KEY, None) or {})

		payload.setdefault("user", _safe_user())
		payload.setdefault("site", getattr(frappe.local, "site", None))

		if record.exc_info:
			payload["exc"] = self.formatException(record.exc_info)

		try:
			return json.dumps(payload, default=str)
		except Exception:
			return json.dumps({"ts": payload["ts"], "level": payload["level"],
			                   "event": payload["event"], "_serialise_error": True})


class _GatePassLogger(logging.LoggerAdapter):
	"""Moves caller-supplied fields into one nested key.

	Call sites keep the natural `logger.info("event", extra={...})` shape; the
	adapter is what keeps that safe.
	"""

	def process(self, msg, kwargs):
		fields = kwargs.pop("extra", None) or {}
		kwargs["extra"] = {_PAYLOAD_KEY: fields}
		return msg, kwargs


def _safe_user() -> str | None:
	try:
		return frappe.session.user
	except Exception:
		return None


def get_logger() -> logging.LoggerAdapter:
	logger = frappe.logger(LOGGER_NAME, allow_site=True, file_count=10)
	if not getattr(logger, "_gatepass_configured", False):
		for handler in logger.handlers:
			handler.setFormatter(_JsonFormatter())
		logger.setLevel(_configured_level())
		logger._gatepass_configured = True
	return _GatePassLogger(logger, {})


def _configured_level() -> int:
	try:
		level = frappe.get_cached_value("Gate Pass Settings", None, "log_level")
		return LEVELS.get(level, logging.INFO)
	except Exception:
		return logging.INFO


def new_trace_id() -> str:
	return frappe.generate_hash(length=12)


def log_failure(event: str, exc: Exception, *, gate_pass: str | None = None, **extra) -> str:
	"""Record a failure everywhere it needs to be, and return the trace id.

	Never swallows. The caller decides whether to re-raise; this only ensures
	the failure is recoverable from the logs regardless of that decision.
	"""
	trace_id = new_trace_id()
	get_logger().error(
		event,
		extra={"trace_id": trace_id, "gate_pass": gate_pass, "error": str(exc), **extra},
	)
	frappe.log_error(
		title=f"Gate Pass: {event}"[:140],
		message=f"trace_id: {trace_id}\n\n{frappe.get_traceback()}",
		reference_doctype="Gate Pass" if gate_pass else None,
		reference_name=gate_pass,
	)
	return trace_id
