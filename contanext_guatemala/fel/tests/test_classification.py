from datetime import datetime
from types import MappingProxyType
from unittest import TestCase

import requests

from contanext_guatemala.fel.classification import (
	result_from_exception,
	result_from_extracted,
	result_from_http_error,
)
from contanext_guatemala.fel.result import ExtractedTekraResult, TekraResultError
from contanext_guatemala.fel.soap import SOAPFaultError, SOAPParseError
from contanext_guatemala.fel.transport import SOAPTransportError
from contanext_guatemala.fel.types import FELErrorClassification, FELStatus


def extracted(error=0, **result_values):
	result = {"error": error, **result_values}
	return ExtractedTekraResult(
		operation="CertificacionDocumentoResponse",
		result=MappingProxyType(result),
		error_code=error,
		certified_xml=b"<xml/>" if error == 0 else None,
		pdf=b"%PDF-" if error == 0 else None,
		uuid="22232DB6-4455-5F22-AA8D-59CD39E80F12" if error == 0 else None,
		series="A" if error == 0 else None,
		number="1" if error == 0 else None,
		certified_at=datetime.fromisoformat("2026-10-30T14:15:16-06:00") if error == 0 else None,
		certifier_nit="107346834" if error == 0 else None,
	)


class TestTekraClassification(TestCase):
	def test_success_preserves_evidence_warnings_and_raw_response(self):
		result = result_from_extracted(
			extracted(frases=["warning"], mensajes_marcas=[{"mensaje": "brand"}]),
			raw_response=b"raw",
		)

		self.assertEqual(result.status, FELStatus.CERTIFIED)
		self.assertEqual(result.error_classification, FELErrorClassification.NONE)
		self.assertEqual(result.warnings, ("warning",))
		self.assertEqual(result.brand_messages, ("brand",))
		self.assertEqual(result.raw_response, b"raw")

	def test_rejections_distinguish_xsd_and_fiscal(self):
		xsd = result_from_extracted(extracted(12, errores_xsd=["invalid schema"]))
		fiscal = result_from_extracted(extracted(13, mensaje="invalid tax rule"))

		self.assertEqual((xsd.status, xsd.error_classification), (FELStatus.REJECTED, FELErrorClassification.XSD_REJECTION))
		self.assertEqual(fiscal.error_classification, FELErrorClassification.FISCAL_REJECTION)
		self.assertEqual(fiscal.errors, ("invalid tax rule",))

	def test_http_matrix_is_explicit_and_conservative(self):
		cases = {
			503: (FELStatus.RETRY_PENDING, FELErrorClassification.TRANSIENT),
			401: (FELStatus.FAILED, FELErrorClassification.PERMANENT_CONFIGURATION),
			500: (FELStatus.RECONCILIATION_REQUIRED, FELErrorClassification.UNCERTAIN),
			404: (FELStatus.FAILED, FELErrorClassification.PERMANENT_PROVIDER),
		}
		for status_code, expected in cases.items():
			with self.subTest(status_code=status_code):
				result = result_from_http_error(status_code)
				self.assertEqual((result.status, result.error_classification), expected)

	def test_transport_before_send_retries_but_possible_send_reconciles(self):
		before_send = result_from_exception(SOAPTransportError("connect", request_may_have_been_sent=False))
		possible_send = result_from_exception(SOAPTransportError("read", request_may_have_been_sent=True))

		self.assertEqual(before_send.status, FELStatus.RETRY_PENDING)
		self.assertEqual(before_send.error_classification, FELErrorClassification.TRANSIENT)
		self.assertEqual(possible_send.status, FELStatus.RECONCILIATION_REQUIRED)
		self.assertEqual(possible_send.error_classification, FELErrorClassification.UNCERTAIN)

	def test_soap_fault_server_retries_and_client_fails(self):
		server = result_from_exception(SOAPFaultError("soap:Server", "temporary"))
		client = result_from_exception(SOAPFaultError("soap:Client", "bad request"))

		self.assertEqual(server.status, FELStatus.RETRY_PENDING)
		self.assertEqual(client.status, FELStatus.FAILED)
		self.assertEqual(client.soap_code, "soap:Client")

	def test_malformed_success_response_is_uncertain(self):
		for error in (SOAPParseError("bad xml"), TekraResultError("bad result")):
			with self.subTest(error=error):
				result = result_from_exception(error, http_status=200, raw_response=b"broken")
				self.assertEqual(result.status, FELStatus.RECONCILIATION_REQUIRED)
				self.assertEqual(result.error_classification, FELErrorClassification.UNCERTAIN)

	def test_unknown_adapter_exception_is_permanent_without_leaking_detail(self):
		result = result_from_exception(requests.RequestException("secret provider detail"))

		self.assertEqual(result.status, FELStatus.FAILED)
		self.assertEqual(result.error_classification, FELErrorClassification.PERMANENT_PROVIDER)
		self.assertNotIn("secret provider detail", result.errors[0])
