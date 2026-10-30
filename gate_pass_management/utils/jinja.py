"""Helpers available in print formats."""

import frappe


def get_compliance_summary(gate_pass: str) -> list[dict]:
	"""Passing statutory numbers, for printing on the gate slip.

	The driver carries the slip; the numbers on it are what an inspection asks
	for, so they belong on the paper rather than only on a screen.
	"""
	if not frappe.db.get_single_value("Gate Pass Settings", "show_compliance_on_print"):
		return []
	return frappe.get_all(
		"Gate Pass Compliance Check",
		filters={"parent": gate_pass, "status": ["in", ["Generated", "Not Required"]]},
		fields=["label", "status", "document_no", "document_date"],
	)


def get_qr_code(gate_pass: str) -> str:
	"""QR encoding the document name only.

	Never a token or a URL carrying credentials: the slip is handed to a driver
	and photographed at checkpoints.
	"""
	if not frappe.db.get_single_value("Gate Pass Settings", "enable_qr_code"):
		return ""
	from frappe.utils.data import get_absolute_url

	import io
	from base64 import b64encode

	buffer = io.BytesIO()
	try:
		import pyqrcode

		pyqrcode.create(gate_pass).png(buffer, scale=4, quiet_zone=1)
	except Exception:
		try:
			import qrcode

			qrcode.make(gate_pass).save(buffer, format="PNG")
		except Exception as exc:
			# A blank space where the QR should be tells nobody anything, and the
			# slip is what the driver carries. Say why it is missing.
			from gate_pass_management.utils.logger import get_logger

			get_logger().warning(
				"qr_code_failed", extra={"gate_pass": gate_pass, "error": str(exc)}
			)
			frappe.log_error(
				title="Gate Pass: QR code could not be generated",
				message=f"Install pyqrcode+pypng or qrcode.\n\n{frappe.get_traceback()}",
				reference_doctype="Gate Pass",
				reference_name=gate_pass,
			)
			return ""

	return f"data:image/png;base64,{b64encode(buffer.getvalue()).decode()}"
