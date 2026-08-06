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


class _JsonFormatter(logging.Formatter):
	RESERVED = {
		"name", "msg", "args", "levelname", "levelno", "pathname", "filename",
		"module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
		"created", "msecs", "relativeCreated", "thread", "threadName",
		"processName", "process", "taskName", "message", "asctime",
	}

	def format(self, record: logging.LogRecord) -> str:
		payload = {
			"ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
			"level": record.levelname,
			"event": record.getMessage(),
		}
		for key, value in record.__dict__.items():
			if key not in self.RESERVED and not key.startswith("_"):
				payload[key] = value

		payload.setdefault("user", _safe_user())
		payload.setdefault("site", getattr(frappe.local, "site", None))

		try:
			return json.dumps(payload, default=str)
		except Exception:
			return json.dumps({"ts": payload["ts"], "level": payload["level"],
			                   "event": payload["event"], "_serialise_error": True})


def _safe_user() -> str | None:
	try:
		return frappe.session.user
	except Exception:
		return None


def get_logger() -> logging.Logger:
	logger = frappe.logger(LOGGER_NAME, allow_site=True, file_count=10)
	if not getattr(logger, "_gatepass_configured", False):
		for handler in logger.handlers:
			handler.setFormatter(_JsonFormatter())
		logger.setLevel(_configured_level())
		logger._gatepass_configured = True
	return logger


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
