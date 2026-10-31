from __future__ import annotations

from typing import Any, Iterable

from contanext_guatemala.fel.result import ExtractedTekraResult, TekraResultError
from contanext_guatemala.fel.settings import FELConfigurationError
from contanext_guatemala.fel.soap import SOAPEnvelopeError, SOAPFaultError, SOAPParseError
from contanext_guatemala.fel.transport import SOAPTransportError
from contanext_guatemala.fel.types import CertificationResult, FELErrorClassification, FELStatus


TRANSIENT_HTTP_STATUSES = frozenset({408, 429, 502, 503, 504})
CONFIGURATION_HTTP_STATUSES = frozenset({401, 403, 407})


def result_from_extracted(
	extracted: ExtractedTekraResult,
	*,
	http_status: int = 200,
	raw_response: bytes | None = None,
) -> CertificationResult:
	common = {
		"uuid": extracted.uuid,
		"series": extracted.series,
		"number": extracted.number,
		"certified_at": extracted.certified_at,
		"certifier_nit": extracted.certifier_nit,
		"certified_xml": extracted.certified_xml,
		"pdf": extracted.pdf,
		"http_status": http_status,
		"warnings": _messages(extracted.result.get("frases")),
		"brand_messages": _messages(extracted.result.get("mensajes_marcas")),
		"xsd_errors": _messages(extracted.result.get("errores_xsd")),
		"normalized_result": dict(extracted.result),
		"raw_response": raw_response,
	}
	if extracted.error_code == 0:
		status = FELStatus.CANCELLED if extracted.operation == "AnulacionDocumentoResponse" else FELStatus.CERTIFIED
		return CertificationResult(status=status, **common)

	xsd_errors = common["xsd_errors"]
	classification = FELErrorClassification.XSD_REJECTION if xsd_errors else FELErrorClassification.FISCAL_REJECTION
	return CertificationResult(
		status=FELStatus.REJECTED,
		error_classification=classification,
		errors=_messages(extracted.result.get("errores") or extracted.result.get("mensaje")),
		**common,
	)


def result_from_http_error(status_code: int, *, raw_response: bytes | None = None) -> CertificationResult:
	if status_code in TRANSIENT_HTTP_STATUSES:
		return _failure(FELStatus.RETRY_PENDING, FELErrorClassification.TRANSIENT, status_code, raw_response)
	if status_code in CONFIGURATION_HTTP_STATUSES:
		return _failure(
			FELStatus.FAILED,
			FELErrorClassification.PERMANENT_CONFIGURATION,
			status_code,
			raw_response,
		)
	if status_code == 500:
		return _failure(FELStatus.RECONCILIATION_REQUIRED, FELErrorClassification.UNCERTAIN, status_code, raw_response)
	return _failure(FELStatus.FAILED, FELErrorClassification.PERMANENT_PROVIDER, status_code, raw_response)


def result_from_exception(
	exc: Exception,
	*,
	http_status: int | None = None,
	raw_response: bytes | None = None,
) -> CertificationResult:
	if isinstance(exc, SOAPTransportError):
		if exc.request_may_have_been_sent:
			return _failure(
				FELStatus.RECONCILIATION_REQUIRED,
				FELErrorClassification.UNCERTAIN,
				http_status,
				raw_response,
				str(exc),
			)
		return _failure(
			FELStatus.RETRY_PENDING,
			FELErrorClassification.TRANSIENT,
			http_status,
			raw_response,
			str(exc),
		)
	if isinstance(exc, SOAPFaultError):
		classification = (
			FELErrorClassification.TRANSIENT
			if exc.code and exc.code.lower().endswith("server")
			else FELErrorClassification.PERMANENT_PROVIDER
		)
		status = FELStatus.RETRY_PENDING if classification == FELErrorClassification.TRANSIENT else FELStatus.FAILED
		return _failure(status, classification, http_status, raw_response, str(exc), soap_code=exc.code)
	if isinstance(exc, (SOAPParseError, TekraResultError)):
		return _failure(
			FELStatus.RECONCILIATION_REQUIRED,
			FELErrorClassification.UNCERTAIN,
			http_status,
			raw_response,
			str(exc),
		)
	if isinstance(exc, (FELConfigurationError, SOAPEnvelopeError)):
		return _failure(
			FELStatus.FAILED,
			FELErrorClassification.PERMANENT_CONFIGURATION,
			http_status,
			raw_response,
			str(exc),
		)
	return _failure(
		FELStatus.FAILED,
		FELErrorClassification.PERMANENT_PROVIDER,
		http_status,
		raw_response,
		"Error no reconocido del adaptador TEKRA.",
	)


def _failure(
	status: FELStatus,
	classification: FELErrorClassification,
	http_status: int | None,
	raw_response: bytes | None,
	message: str | None = None,
	*,
	soap_code: str | None = None,
) -> CertificationResult:
	return CertificationResult(
		status=status,
		error_classification=classification,
		http_status=http_status,
		soap_code=soap_code,
		errors=(message,) if message else (),
		raw_response=raw_response,
	)


def _messages(value: Any) -> tuple[str, ...]:
	if value is None or value == "":
		return ()
	items: Iterable[Any] = value if isinstance(value, (list, tuple)) else (value,)
	messages = []
	for item in items:
		if isinstance(item, dict):
			message = item.get("mensaje") or item.get("message") or str(item)
		else:
			message = str(item)
		message = message.strip()
		if message:
			messages.append(message[:1000])
	return tuple(messages)
