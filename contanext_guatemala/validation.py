from __future__ import annotations

import re

NIT_PATTERN = re.compile(r"^[0-9]{1,11}-?[0-9K]$")


def normalize_nit(value: str | None) -> str:
	"""Normalize a Guatemalan NIT without claiming verification against SAT."""
	return re.sub(r"\s+", "", (value or "").upper())


def is_valid_nit_format(value: str | None) -> bool:
	"""Return whether a non-empty value has an accepted NIT syntax."""
	return bool(NIT_PATTERN.fullmatch(normalize_nit(value)))


def validate_nit_format(value: str | None, *, allow_empty: bool = False) -> str:
	"""Normalize and validate syntax only, never the NIT's status before SAT."""
	nit = normalize_nit(value)
	if not nit and allow_empty:
		return ""
	if not is_valid_nit_format(nit):
		raise ValueError("Formato de NIT inválido")
	return nit
