from unittest import TestCase

from lxml import etree

from contanext_guatemala.fel.soap import (
	SOAPEnvelopeError,
	SOAPFaultError,
	SOAPParseError,
	TekraSOAPCredentials,
	build_cancellation_envelope,
	build_certification_envelope,
	parse_soap_response,
)


CREDENTIALS = TekraSOAPCredentials(
	user="user&name",
	password="secret<value>",
	client="123",
	contract="456",
	origin_id="ContaNext",
	origin_ip="127.0.0.1",
)
DTE = b'<?xml version="1.0" encoding="UTF-8"?><dte:GTDocumento xmlns:dte="urn:dte"><dte:Nombre>A &amp; B</dte:Nombre></dte:GTDocumento>'


class TestTekraSOAPEnvelope(TestCase):
	def test_certification_uses_cdata_and_escapes_credentials(self):
		envelope = build_certification_envelope(CREDENTIALS, DTE)
		text = envelope.decode()

		self.assertIn("<![CDATA[<?xml", text)
		self.assertIn("<dte:GTDocumento", text)
		self.assertNotIn("&lt;dte:GTDocumento", text)
		self.assertIn("user&amp;name", text)
		self.assertIn("secret&lt;value&gt;", text)
		self.assertIn("<pn_validar_identificador>SI</pn_validar_identificador>", text)
		self.assertIn("<pn_retornar_pdf>SI</pn_retornar_pdf>", text)
		etree.fromstring(envelope)

	def test_cancellation_omits_certification_only_fields(self):
		envelope = build_cancellation_envelope(CREDENTIALS, DTE).decode()

		self.assertIn("AnulacionDocumento", envelope)
		self.assertNotIn("pn_validar_identificador", envelope)
		self.assertNotIn("pn_id_origen", envelope)
		self.assertNotIn("pn_ip_origen", envelope)

	def test_rejects_empty_non_utf8_document_and_missing_credentials(self):
		for document in (b"", b"\xff"):
			with self.subTest(document=document):
				with self.assertRaises(SOAPEnvelopeError):
					build_certification_envelope(CREDENTIALS, document)

		with self.assertRaisesRegex(SOAPEnvelopeError, "pn_usuario"):
			build_certification_envelope(
				TekraSOAPCredentials("", "password", "1", "2", "origin", "127.0.0.1"),
				DTE,
			)


class TestTekraSOAPParser(TestCase):
	def test_parses_text_and_nested_xml_without_interpreting_business_result(self):
		payload = b"""<?xml version="1.0"?>
		<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:t="urn:tekra" xmlns:d="urn:dte">
		  <soap:Body><t:CertificacionDocumentoResponse>
		    <ResultadoCertificacion>{"error":0}</ResultadoCertificacion>
		    <DocumentoCertificado><d:GTDocumento><d:SAT/></d:GTDocumento></DocumentoCertificado>
		    <RepresentacionGrafica>JVBERg==</RepresentacionGrafica>
		  </t:CertificacionDocumentoResponse></soap:Body>
		</soap:Envelope>"""

		parsed = parse_soap_response(payload)

		self.assertEqual(parsed.operation, "CertificacionDocumentoResponse")
		self.assertEqual(parsed.fields["ResultadoCertificacion"], '{"error":0}')
		self.assertIn("GTDocumento", parsed.fields["DocumentoCertificado"])
		self.assertEqual(parsed.fields["RepresentacionGrafica"], "JVBERg==")

	def test_rejects_dtd_entities_and_non_soap_xml(self):
		payloads = (
			b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><x>&e;</x>',
			b"<root/>",
		)
		for payload in payloads:
			with self.subTest(payload=payload):
				with self.assertRaises(SOAPParseError):
					parse_soap_response(payload)

	def test_raises_sanitized_soap_fault(self):
		payload = b"""<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
		<soap:Body><soap:Fault><faultcode>soap:Server</faultcode><faultstring>Temporary failure</faultstring></soap:Fault></soap:Body>
		</soap:Envelope>"""

		with self.assertRaises(SOAPFaultError) as captured:
			parse_soap_response(payload)

		self.assertEqual(captured.exception.code, "soap:Server")
		self.assertEqual(captured.exception.fault_message, "Temporary failure")
