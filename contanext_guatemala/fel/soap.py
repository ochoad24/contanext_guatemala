from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from lxml import etree


SOAP_ENVELOPE_NS = "http://schemas.xmlsoap.org/soap/envelope/"
TEKRA_SERVICE_NS = "http://apicertificacion.desa.tekra.com.gt:8080/certificacion/wsdl/"
FORBIDDEN_XML_MARKERS = (b"<!DOCTYPE", b"<!ENTITY")


@dataclass(frozen=True, slots=True)
class TekraSOAPCredentials:
	user: str
	password: str
	client: str
	contract: str
	origin_id: str
	origin_ip: str
	sign_issuer: bool = True


@dataclass(frozen=True, slots=True)
class ParsedSOAPResponse:
	operation: str
	fields: Mapping[str, str]


class SOAPEnvelopeError(ValueError):
	pass


class SOAPParseError(ValueError):
	pass


class SOAPFaultError(SOAPParseError):
	def __init__(self, code: str | None, message: str | None):
		self.code = code
		self.fault_message = message
		summary = ": ".join(value for value in (code, message) if value) or "sin detalle"
		super().__init__(f"TEKRA devolvió un SOAP Fault: {summary[:500]}")


def build_certification_envelope(
	credentials: TekraSOAPCredentials,
	document_xml: bytes,
	*,
	service_namespace: str = TEKRA_SERVICE_NS,
) -> bytes:
	return _build_envelope(
		"CertificacionDocumento",
		credentials,
		document_xml,
		service_namespace=service_namespace,
		include_origin=True,
		validate_identifier=True,
	)


def build_cancellation_envelope(
	credentials: TekraSOAPCredentials,
	document_xml: bytes,
	*,
	service_namespace: str = TEKRA_SERVICE_NS,
) -> bytes:
	return _build_envelope(
		"AnulacionDocumento",
		credentials,
		document_xml,
		service_namespace=service_namespace,
		include_origin=False,
		validate_identifier=False,
	)


def parse_soap_response(payload: bytes) -> ParsedSOAPResponse:
	if not payload.strip():
		raise SOAPParseError("La respuesta SOAP está vacía.")
	upper_payload = payload.upper()
	if any(marker in upper_payload for marker in FORBIDDEN_XML_MARKERS):
		raise SOAPParseError("La respuesta SOAP contiene DTD o entidades no permitidas.")

	parser = etree.XMLParser(
		resolve_entities=False,
		load_dtd=False,
		no_network=True,
		recover=False,
		huge_tree=False,
		remove_comments=True,
	)
	try:
		root = etree.fromstring(payload, parser=parser)
	except (etree.XMLSyntaxError, ValueError) as exc:
		raise SOAPParseError("La respuesta SOAP no contiene XML válido.") from exc

	if root.tag != f"{{{SOAP_ENVELOPE_NS}}}Envelope":
		raise SOAPParseError("La respuesta no es un envelope SOAP 1.1.")
	body = root.find(f"{{{SOAP_ENVELOPE_NS}}}Body")
	if body is None:
		raise SOAPParseError("La respuesta SOAP no contiene Body.")

	fault = body.find(f"{{{SOAP_ENVELOPE_NS}}}Fault")
	if fault is not None:
		raise SOAPFaultError(_child_text(fault, "faultcode"), _child_text(fault, "faultstring"))

	response_nodes = [child for child in body if isinstance(child.tag, str)]
	if len(response_nodes) != 1:
		raise SOAPParseError("El Body SOAP debe contener una única respuesta.")
	response = response_nodes[0]
	fields = {_local_name(child): _element_content(child) for child in response if isinstance(child.tag, str)}
	return ParsedSOAPResponse(operation=_local_name(response), fields=MappingProxyType(fields))


def _build_envelope(
	operation: str,
	credentials: TekraSOAPCredentials,
	document_xml: bytes,
	*,
	service_namespace: str,
	include_origin: bool,
	validate_identifier: bool,
) -> bytes:
	try:
		document_text = document_xml.decode("utf-8")
	except UnicodeDecodeError as exc:
		raise SOAPEnvelopeError("El documento TEKRA debe estar codificado en UTF-8.") from exc
	if not document_text.strip():
		raise SOAPEnvelopeError("El documento TEKRA no puede estar vacío.")

	envelope = etree.Element(f"{{{SOAP_ENVELOPE_NS}}}Envelope", nsmap={"soapenv": SOAP_ENVELOPE_NS})
	body = etree.SubElement(envelope, f"{{{SOAP_ENVELOPE_NS}}}Body")
	request = etree.SubElement(body, f"{{{service_namespace}}}{operation}", nsmap={"tek": service_namespace})
	authentication = etree.SubElement(request, "Autenticacion")
	_add_text(authentication, "pn_usuario", credentials.user)
	_add_text(authentication, "pn_clave", credentials.password)
	_add_text(authentication, "pn_cliente", credentials.client)
	_add_text(authentication, "pn_contrato", credentials.contract)
	if include_origin:
		_add_text(authentication, "pn_id_origen", credentials.origin_id)
		_add_text(authentication, "pn_ip_origen", credentials.origin_ip)
	_add_text(authentication, "pn_firmar_emisor", "SI" if credentials.sign_issuer else "NO")
	if validate_identifier:
		_add_text(authentication, "pn_validar_identificador", "SI")
	_add_text(authentication, "pn_retornar_pdf", "SI")
	document = etree.SubElement(request, "Documento")
	document.text = etree.CDATA(document_text)
	return etree.tostring(envelope, encoding="UTF-8", xml_declaration=True)


def _add_text(parent, name: str, value: str) -> None:
	if not value or not value.strip():
		raise SOAPEnvelopeError(f"El parámetro {name} es obligatorio.")
	element = etree.SubElement(parent, name)
	element.text = value


def _child_text(parent, local_name: str) -> str | None:
	for child in parent:
		if isinstance(child.tag, str) and _local_name(child) == local_name:
			return (child.text or "").strip() or None
	return None


def _local_name(element) -> str:
	return etree.QName(element).localname


def _element_content(element) -> str:
	if len(element):
		return "".join(etree.tostring(child, encoding="unicode") for child in element)
	return element.text or ""
