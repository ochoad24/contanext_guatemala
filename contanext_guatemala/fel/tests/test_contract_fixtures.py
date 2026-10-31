from pathlib import Path
from unittest import TestCase

from contanext_guatemala.fel.classification import result_from_exception, result_from_extracted
from contanext_guatemala.fel.result import TekraResultError, extract_tekra_result
from contanext_guatemala.fel.soap import SOAPFaultError, SOAPParseError, parse_soap_response
from contanext_guatemala.fel.types import FELErrorClassification, FELStatus


FIXTURES = Path(__file__).with_name("fixtures") / "tekra"


def load_fixture(name: str) -> bytes:
	return (FIXTURES / name).read_bytes()


class TestTekraContractFixtures(TestCase):
	def test_recorded_shape_success_is_certified(self):
		payload = load_fixture("success.xml")
		result = result_from_extracted(extract_tekra_result(parse_soap_response(payload)), raw_response=payload)

		self.assertEqual(result.status, FELStatus.CERTIFIED)
		self.assertEqual(result.uuid, "11111111-2222-3333-4444-555555555555")
		self.assertTrue(result.pdf.startswith(b"%PDF-"))

	def test_xsd_rejection_is_not_retried(self):
		payload = load_fixture("rejection_xsd.xml")
		result = result_from_extracted(extract_tekra_result(parse_soap_response(payload)), raw_response=payload)

		self.assertEqual(result.status, FELStatus.REJECTED)
		self.assertEqual(result.error_classification, FELErrorClassification.XSD_REJECTION)

	def test_success_preserves_warning_channels(self):
		payload = load_fixture("warnings.xml")
		result = result_from_extracted(extract_tekra_result(parse_soap_response(payload)))

		self.assertEqual(result.warnings, ("Fixture warning",))
		self.assertEqual(result.brand_messages, ("Fixture brand warning",))

	def test_soap_fault_server_is_transient(self):
		with self.assertRaises(SOAPFaultError) as captured:
			parse_soap_response(load_fixture("soap_fault.xml"))

		result = result_from_exception(captured.exception, http_status=500)
		self.assertEqual(result.status, FELStatus.RETRY_PENDING)
		self.assertEqual(result.error_classification, FELErrorClassification.TRANSIENT)

	def test_corrupt_success_fixtures_require_reconciliation(self):
		for name in ("empty_xml_success.xml", "invalid_base64.xml", "invalid_pdf.xml"):
			with self.subTest(name=name):
				payload = load_fixture(name)
				parsed = parse_soap_response(payload)
				with self.assertRaises(TekraResultError) as captured:
					extract_tekra_result(parsed)
				result = result_from_exception(captured.exception, http_status=200, raw_response=payload)
				self.assertEqual(result.status, FELStatus.RECONCILIATION_REQUIRED)

	def test_truncated_response_requires_reconciliation(self):
		payload = load_fixture("truncated.xml")
		with self.assertRaises(SOAPParseError) as captured:
			parse_soap_response(payload)

		result = result_from_exception(captured.exception, http_status=200, raw_response=payload)
		self.assertEqual(result.status, FELStatus.RECONCILIATION_REQUIRED)
