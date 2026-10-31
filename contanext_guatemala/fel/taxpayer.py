from __future__ import annotations

import re

import frappe


def normalize_taxpayer_identifier(identification_type: str, identifier: str) -> str:
	kind = (identification_type or "").strip().upper()
	raw = (identifier or "").strip().upper()
	if kind == "NIT":
		normalized = re.sub(r"[^0-9K]", "", raw)
		if len(normalized) < 2:
			raise ValueError("El NIT no tiene un formato consultable.")
		return normalized
	if kind == "CUI":
		normalized = re.sub(r"\D", "", raw)
		if len(normalized) != 13:
			raise ValueError("El CUI debe contener 13 dígitos.")
		return normalized
	if kind in {"CF", "EXT"}:
		return raw
	if not kind:
		return ""
	raise ValueError("Tipo de identificación FEL no soportado.")


def taxpayer_lookup_key(provider: str, environment: str, identification_type: str, normalized_identifier: str) -> str:
	parts = (
		(provider or "").strip().upper(),
		(environment or "").strip().upper(),
		(identification_type or "").strip().upper(),
		(normalized_identifier or "").strip().upper(),
	)
	if not all(parts):
		raise ValueError("Proveedor, ambiente, tipo e identificador son obligatorios.")
	return "::".join(parts)


def invalidate_customer_validation_on_identity_change(doc, method=None) -> None:
	if doc.is_new():
		return
	previous = doc.get_doc_before_save()
	if not previous:
		return
	if (
		(doc.tax_id or "").strip() == (previous.tax_id or "").strip()
		and (doc.contanext_gt_identification_type or "") == (previous.contanext_gt_identification_type or "")
	):
		return
	doc.contanext_gt_taxpayer_validation = None
	doc.contanext_gt_taxpayer_validation_status = None
	doc.contanext_gt_taxpayer_returned_name = None
