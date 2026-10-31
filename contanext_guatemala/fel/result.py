from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import Any, Mapping

from lxml import etree

from contanext_guatemala.fel.soap import ParsedSOAPResponse, SOAPParseError


UUID_PATTERN = re.compile(r"^[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}$", re.IGNORECASE)
CERTIFICATION_RESULT_FIELDS = ("ResultadoCertificacion", "ResultadoAnulacion")
CERTIFIED_DOCUMENT_FIELDS = ("DocumentoCertificado", "AnulacionCertificada")


@dataclass(frozen=True, slots=True)
class ExtractedTekraResult:
	operation: str
	result: Mapping[str, Any]
	error_code: int
	certified_xml: bytes | None = None
	pdf: bytes | None = None
	uuid: str | None = None
	series: str | None = None
	number: str | None = None
	certified_at: datetime | None = None
	certifier_nit: str | None = None


class TekraResultError(ValueError):
	pass


def extract_tekra_result(response: ParsedSOAPResponse) -> ExtractedTekraResult:
	result_text = _first_present(response.fields, CERTIFICATION_RESULT_FIELDS)
	if result_text is None:
		raise TekraResultError("La respuesta TEKRA no contiene un resultado JSON.")
	try:
		result = json.loads(result_text)
	except (json.JSONDecodeError, TypeError) as exc:
		raise TekraResultError("El resultado TEKRA no contiene JSON válido.") from exc
	if not isinstance(result, dict):
		raise TekraResultError("El resultado TEKRA debe ser un objeto JSON.")
	error_code = _parse_error_code(result.get("error"))

	certified_xml = _extract_certified_xml(response.fields)
	metadata = _extract_certification_metadata(certified_xml) if certified_xml else {}
	pdf = _decode_pdf(response.fields.get("RepresentacionGrafica"))

	uuid = _consistent_value("UUID", metadata.get("uuid"), response.fields.get("NumeroAutorizacion"))
	series = _consistent_value("serie", metadata.get("series"), response.fields.get("SerieDocumento"))
	number = _consistent_value("número", metadata.get("number"), response.fields.get("NumeroDocumento"))
	certifier_nit = _consistent_value("NIT certificador", metadata.get("certifier_nit"), response.fields.get("NITCertificador"))
	certified_at_text = _consistent_value(
		"fecha de certificación",
		metadata.get("certified_at"),
		response.fields.get("FechaHoraCertificacion"),
	)

	if uuid and not UUID_PATTERN.fullmatch(uuid):
		raise TekraResultError("El UUID retornado por TEKRA no tiene un formato válido.")
	certified_at = _parse_certified_at(certified_at_text) if certified_at_text else None
	if error_code == 0 and response.operation == "CertificacionDocumentoResponse":
		missing = [
			label
			for label, value in (
				("XML certificado", certified_xml),
				("PDF", pdf),
				("UUID", uuid),
				("serie", series),
				("número", number),
				("fecha de certificación", certified_at),
				("NIT certificador", certifier_nit),
			)
			if value is None
		]
		if missing:
			raise TekraResultError("La certificación exitosa no contiene: " + ", ".join(missing) + ".")
	return ExtractedTekraResult(
		operation=response.operation,
		result=MappingProxyType(result),
		error_code=error_code,
		certified_xml=certified_xml,
		pdf=pdf,
		uuid=uuid.upper() if uuid else None,
		series=series,
		number=number,
		certified_at=certified_at,
		certifier_nit=certifier_nit,
	)


def _parse_error_code(value: Any) -> int:
	if isinstance(value, bool):
		raise TekraResultError("El campo error de TEKRA debe ser numérico.")
	if isinstance(value, int):
		return value
	if isinstance(value, str) and value.strip().lstrip("-").isdigit():
		return int(value)
	raise TekraResultError("El resultado TEKRA no contiene un campo error numérico.")


def _extract_certified_xml(fields: Mapping[str, str]) -> bytes | None:
	value = _first_present(fields, CERTIFIED_DOCUMENT_FIELDS)
	if not value or not value.strip():
		return None
	payload = value.strip().encode("utf-8")
	try:
		root = etree.fromstring(
			payload,
			parser=etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False),
		)
	except (etree.XMLSyntaxError, ValueError) as exc:
		raise TekraResultError("El documento certificado retornado por TEKRA no contiene XML válido.") from exc
	return etree.tostring(root, encoding="UTF-8", xml_declaration=True)


def _extract_certification_metadata(certified_xml: bytes) -> dict[str, str]:
	try:
		root = etree.fromstring(
			certified_xml,
			parser=etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, huge_tree=False),
		)
	except (etree.XMLSyntaxError, ValueError) as exc:
		raise SOAPParseError("No fue posible releer el XML certificado.") from exc

	authorization = _find_by_local_name(root, "NumeroAutorizacion")
	certified_at = _find_by_local_name(root, "FechaHoraCertificacion")
	certifier_nit = _find_by_local_name(root, "NITCertificador")
	metadata: dict[str, str] = {}
	if authorization is not None:
		metadata["uuid"] = (authorization.text or "").strip()
		metadata["series"] = (authorization.get("Serie") or "").strip()
		metadata["number"] = (authorization.get("Numero") or "").strip()
	if certified_at is not None:
		metadata["certified_at"] = (certified_at.text or "").strip()
	if certifier_nit is not None:
		metadata["certifier_nit"] = (certifier_nit.text or "").strip()
	return {key: value for key, value in metadata.items() if value}


def _decode_pdf(value: str | None) -> bytes | None:
	if not value or not value.strip():
		return None
	try:
		pdf = base64.b64decode("".join(value.split()), validate=True)
	except (binascii.Error, ValueError) as exc:
		raise TekraResultError("La representación gráfica TEKRA no contiene Base64 válido.") from exc
	if not pdf.startswith(b"%PDF-"):
		raise TekraResultError("La representación gráfica TEKRA no es un PDF válido.")
	return pdf


def _parse_certified_at(value: str) -> datetime:
	try:
		parsed = datetime.fromisoformat(value)
	except ValueError as exc:
		raise TekraResultError("La fecha de certificación TEKRA no es ISO 8601 válida.") from exc
	if parsed.tzinfo is None or parsed.utcoffset() is None:
		raise TekraResultError("La fecha de certificación TEKRA debe incluir zona horaria.")
	return parsed


def _consistent_value(label: str, *values: str | None) -> str | None:
	normalized = [value.strip() for value in values if value and value.strip()]
	if not normalized:
		return None
	if any(value != normalized[0] for value in normalized[1:]):
		raise TekraResultError(f"TEKRA retornó valores inconsistentes para {label}.")
	return normalized[0]


def _first_present(fields: Mapping[str, str], names: tuple[str, ...]) -> str | None:
	for name in names:
		value = fields.get(name)
		if value is not None:
			return value
	return None


def _find_by_local_name(root, local_name: str):
	for element in root.iter():
		if isinstance(element.tag, str) and etree.QName(element).localname == local_name:
			return element
	return None
