from __future__ import annotations

import re

NIT_PATTERN = re.compile(r"^(?:CF|[0-9]{1,11}-?[0-9K])$", re.IGNORECASE)


def normalize_nit(value: str) -> str:
	return value.strip().upper().replace(" ", "")


def validate_nit_format(value: str) -> str:
	"""Validate syntax only; authoritative validation belongs to SAT/provider services."""
	nit = normalize_nit(value)
	if not NIT_PATTERN.fullmatch(nit):
		raise ValueError("Formato de NIT inválido")
	return nit
