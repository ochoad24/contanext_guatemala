import base64
from types import SimpleNamespace
from unittest import TestCase

from contanext_guatemala.fel.provider import FELProviderPermanentError
from contanext_guatemala.fel.tekra import TekraFELProvider
from contanext_guatemala.fel.types import (
	CancellationRequest,
	CertificationRequest,
	DTEType,
	FELErrorClassification,
	FELStatus,
	ReconciliationRequest,
)


UUID = "22232DB6-4455-5F22-AA8D-59CD39E80F12"
CERTIFIED_XML = f"""<dte:GTDocumento xmlns:dte="http://www.sat.gob.gt/dte/fel/0.2.1"><dte:SAT><dte:DTE>
<dte:Certificacion><dte:NITCertificador>107346834</dte:NITCertificador>
<dte:NumeroAutorizacion Serie="A" Numero="1">{UUID}</dte:NumeroAutorizacion>
<dte:FechaHoraCertificacion>2026-10-30T14:15:16-06:00</dte:FechaHoraCertificacion>
</dte:Certificacion></dte:DTE></dte:SAT></dte:GTDocumento>"""


class FakeResponse:
	def __init__(self, body, status_code=200):
		self.body = body
		self.status_code = status_code
		self.headers = {"Content-Type": "text/xml"}

	def iter_content(self, chunk_size):
		yield self.body

	def close(self):
		pass


class RecordingSession:
	def __init__(self, response):
		self.response = response
		self.calls = []

	def post(self, url, **kwargs):
		self.calls.append((url, kwargs))
		return self.response


ENV = {
	"TEKRA_FEL_USER": "user",
	"TEKRA_FEL_PASSWORD": "secret",
	"TEKRA_FEL_CLIENT": "123",
	"TEKRA_FEL_CONTRACT": "456",
	"TEKRA_FEL_COMPANY_ID": "company",
	"TEKRA_FEL_SANDBOX_URL": "https://sandbox.invalid/soap",
}
CONFIGURATION = SimpleNamespace(environment="SANDBOX", origin_id="ContaNext", sign_issuer=True)


def soap_response(result_json='{"error":0}', certified_xml=CERTIFIED_XML, pdf=b"%PDF-1.7\nfixture"):
	return f"""<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:t="urn:tekra">
<soap:Body><t:CertificacionDocumentoResponse>
<ResultadoCertificacion>{result_json}</ResultadoCertificacion>
<DocumentoCertificado><![CDATA[{certified_xml}]]></DocumentoCertificado>
<RepresentacionGrafica>{base64.b64encode(pdf).decode()}</RepresentacionGrafica>
<NITCertificador>107346834</NITCertificador><NumeroAutorizacion>{UUID}</NumeroAutorizacion>
<NumeroDocumento>1</NumeroDocumento><SerieDocumento>A</SerieDocumento>
<FechaHoraCertificacion>2026-10-30T14:15:16-06:00</FechaHoraCertificacion>
</t:CertificacionDocumentoResponse></soap:Body></soap:Envelope>""".encode()


class TestTekraFELProvider(TestCase):
	def test_certify_composes_transport_and_returns_certified_result(self):
		session = RecordingSession(FakeResponse(soap_response()))
		provider = TekraFELProvider(CONFIGURATION, environ=ENV, session=session)
		request = CertificationRequest(
			document_type=DTEType.FACT,
			external_id="INV-1",
			idempotency_key="stable-id",
			xml=b"<dte:GTDocumento xmlns:dte='urn:dte'/>",
			metadata={"origin_ip": "127.0.0.1"},
		)

		result = provider.certify(request)

		self.assertEqual(result.status, FELStatus.CERTIFIED)
		self.assertEqual(result.uuid, UUID)
		envelope = session.calls[0][1]["data"].decode()
		self.assertIn("<pn_usuario>user</pn_usuario>", envelope)
		self.assertIn("<pn_validar_identificador>SI</pn_validar_identificador>", envelope)
		self.assertIn("<![CDATA[<dte:GTDocumento", envelope)

	def test_http_and_configuration_failures_return_normalized_results(self):
		http_provider = TekraFELProvider(CONFIGURATION, environ=ENV, session=RecordingSession(FakeResponse(b"busy", 503)))
		request = CertificationRequest(DTEType.FACT, "INV-1", "stable-id", b"<dte/>", metadata={"origin_ip": "127.0.0.1"})
		http_result = http_provider.certify(request)

		configuration_provider = TekraFELProvider(CONFIGURATION, environ={**ENV, "TEKRA_FEL_PASSWORD": ""})
		configuration_result = configuration_provider.certify(request)

		self.assertEqual(http_result.status, FELStatus.RETRY_PENDING)
		self.assertEqual(http_result.error_classification, FELErrorClassification.TRANSIENT)
		self.assertEqual(configuration_result.status, FELStatus.FAILED)
		self.assertEqual(configuration_result.error_classification, FELErrorClassification.PERMANENT_CONFIGURATION)

	def test_reconciliation_remains_manual_and_closed(self):
		provider = TekraFELProvider(CONFIGURATION, environ=ENV)
		with self.assertRaises(FELProviderPermanentError):
			provider.reconcile(ReconciliationRequest(idempotency_key="stable-id"))

	def test_cancellation_uses_anulation_envelope(self):
		body = soap_response().replace(b"CertificacionDocumentoResponse", b"AnulacionDocumentoResponse")
		body = body.replace(b"ResultadoCertificacion", b"ResultadoAnulacion")
		body = body.replace(b"DocumentoCertificado", b"AnulacionCertificada")
		session = RecordingSession(FakeResponse(body))
		provider = TekraFELProvider(CONFIGURATION, environ=ENV, session=session)

		result = provider.cancel(CancellationRequest(UUID, "reason", b"<dte:GTAnulacionDocumento xmlns:dte='urn:dte'/>", metadata={"origin_ip": "127.0.0.1"}))

		self.assertEqual(result.status, FELStatus.CANCELLED)
		envelope = session.calls[0][1]["data"].decode()
		self.assertIn("AnulacionDocumento", envelope)
		self.assertNotIn("pn_validar_identificador", envelope)
