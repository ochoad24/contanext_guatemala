import base64
from datetime import timedelta
from types import MappingProxyType
from unittest import TestCase

from contanext_guatemala.fel.result import TekraResultError, extract_tekra_result
from contanext_guatemala.fel.soap import ParsedSOAPResponse


UUID = "22232DB6-4455-5F22-AA8D-59CD39E80F12"
CERTIFIED_XML = f"""<dte:GTDocumento xmlns:dte="http://www.sat.gob.gt/dte/fel/0.2.1">
<dte:SAT><dte:DTE><dte:Certificacion>
<dte:NITCertificador>107346834</dte:NITCertificador>
<dte:NumeroAutorizacion Serie="22232DB6" Numero="44555">{UUID}</dte:NumeroAutorizacion>
<dte:FechaHoraCertificacion>2026-10-30T14:15:16-06:00</dte:FechaHoraCertificacion>
</dte:Certificacion></dte:DTE></dte:SAT></dte:GTDocumento>"""


def response(**overrides):
	fields = {
		"ResultadoCertificacion": '{"error":0,"frases":[],"mensajes_marcas":[]}',
		"DocumentoCertificado": CERTIFIED_XML,
		"RepresentacionGrafica": base64.b64encode(b"%PDF-1.7\nfixture").decode(),
		"NumeroAutorizacion": UUID,
		"SerieDocumento": "22232DB6",
		"NumeroDocumento": "44555",
		"FechaHoraCertificacion": "2026-10-30T14:15:16-06:00",
		"NITCertificador": "107346834",
	}
	fields.update(overrides)
	return ParsedSOAPResponse("CertificacionDocumentoResponse", MappingProxyType(fields))


class TestTekraResultExtraction(TestCase):
	def test_extracts_and_cross_validates_certification_evidence(self):
		result = extract_tekra_result(response())

		self.assertEqual(result.error_code, 0)
		self.assertEqual(result.uuid, UUID)
		self.assertEqual(result.series, "22232DB6")
		self.assertEqual(result.number, "44555")
		self.assertEqual(result.certifier_nit, "107346834")
		self.assertEqual(result.certified_at.utcoffset(), timedelta(hours=-6))
		self.assertTrue(result.certified_xml.startswith(b"<?xml"))
		self.assertTrue(result.pdf.startswith(b"%PDF-"))

	def test_allows_rejection_without_certified_artifacts(self):
		result = extract_tekra_result(
			response(
				ResultadoCertificacion='{"error":12,"errores_xsd":["invalid"]}',
				DocumentoCertificado="",
				RepresentacionGrafica="",
				NumeroAutorizacion="",
				SerieDocumento="",
				NumeroDocumento="",
				FechaHoraCertificacion="",
				NITCertificador="",
			)
		)

		self.assertEqual(result.error_code, 12)
		self.assertIsNone(result.uuid)
		self.assertIsNone(result.pdf)

	def test_success_requires_complete_certification_evidence(self):
		with self.assertRaisesRegex(TekraResultError, "PDF"):
			extract_tekra_result(response(RepresentacionGrafica=""))

	def test_rejects_invalid_json_error_uuid_date_pdf_and_inconsistent_fields(self):
		cases = (
			{"ResultadoCertificacion": "not-json"},
			{"ResultadoCertificacion": '{"error":"unknown"}'},
			{"ResultadoCertificacion": '{"error":1.5}'},
			{"NumeroAutorizacion": "not-a-uuid", "DocumentoCertificado": ""},
			{"FechaHoraCertificacion": "2026-10-30T14:15:16", "DocumentoCertificado": ""},
			{"RepresentacionGrafica": "not-base64"},
			{"SerieDocumento": "DIFFERENT"},
		)
		for overrides in cases:
			with self.subTest(overrides=overrides):
				with self.assertRaises(TekraResultError):
					extract_tekra_result(response(**overrides))
