"""Tracking ID templates.

A template is plain text with `{{ field }}` placeholders and nothing more. It is
stored in Gate Pass Settings, edited by an administrator, and used to build an id
for every gate pass, so it must not be an expression language: handing stored
text to a template engine lets whoever can edit the setting run code inside the
server. Only the fields listed here can be named, and anything else is refused.
"""

import re

# The values a template may use, in the order Gate Pass Settings documents them.
FIELDS = ("party_code", "party", "reference_no", "vehicle_number", "posting_date", "direction")

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


def check(template: str) -> None:
	"""Raise ValueError, saying what is wrong, unless the template is acceptable."""
	unknown = sorted({name for name in _PLACEHOLDER.findall(template) if name not in FIELDS})
	if unknown:
		raise ValueError(
			"unknown field {0}. The fields you can use are: {1}.".format(
				", ".join(unknown), ", ".join(FIELDS)
			)
		)

	if re.search(r"\{\{|\}\}|\{%|%\}|\{#|#\}", _PLACEHOLDER.sub("", template)):
		raise ValueError(
			"only {{ field }} placeholders are supported, with no filters, expressions or blocks."
		)


def render(template: str, context: dict) -> str:
	"""The template with each placeholder replaced by its value, blank if it has none."""
	check(template)
	return _PLACEHOLDER.sub(lambda m: str(context.get(m.group(1)) or ""), template).strip()
