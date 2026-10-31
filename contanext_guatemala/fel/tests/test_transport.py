from unittest import TestCase

import requests

from contanext_guatemala.fel.settings import TekraEnvironmentSettings
from contanext_guatemala.fel.transport import (
	SOAPResponseTooLarge,
	SOAPTransportError,
	TekraSOAPTransport,
)


class FakeResponse:
	def __init__(self, chunks=(), *, status_code=200, headers=None):
		self.chunks = chunks
		self.status_code = status_code
		self.headers = headers or {}
		self.closed = False

	def iter_content(self, chunk_size):
		self.chunk_size = chunk_size
		yield from self.chunks

	def close(self):
		self.closed = True


class FakeSession:
	def __init__(self, result):
		self.result = result
		self.calls = []

	def post(self, url, **kwargs):
		self.calls.append((url, kwargs))
		if isinstance(self.result, Exception):
			raise self.result
		return self.result


def settings(max_response_bytes=1024):
	return TekraEnvironmentSettings(
		environment="SANDBOX",
		endpoint="https://sandbox.invalid/soap",
		connect_timeout_seconds=5,
		read_timeout_seconds=30,
		max_response_bytes=max_response_bytes,
		user="user",
		password="password",
		client="123",
		contract="456",
		certify_soap_action="urn:certify",
		cancel_soap_action="urn:cancel",
	)


class TestTekraSOAPTransport(TestCase):
	def test_posts_soap_11_with_split_timeouts_and_no_redirects(self):
		response = FakeResponse([b"<soap/>"] , headers={"Content-Type": "text/xml"})
		session = FakeSession(response)
		transport = TekraSOAPTransport(settings(), session=session)

		result = transport.post(soap_action="urn:certify", envelope=b"<envelope/>")

		self.assertEqual(result.status_code, 200)
		self.assertEqual(result.body, b"<soap/>")
		self.assertEqual(result.content_type, "text/xml")
		url, kwargs = session.calls[0]
		self.assertEqual(url, "https://sandbox.invalid/soap")
		self.assertEqual(kwargs["timeout"], (5, 30))
		self.assertFalse(kwargs["allow_redirects"])
		self.assertTrue(kwargs["stream"])
		self.assertEqual(kwargs["headers"]["SOAPAction"], '"urn:certify"')
		self.assertEqual(kwargs["data"], b"<envelope/>")
		self.assertTrue(response.closed)

	def test_connect_timeout_is_safe_to_retry_and_redacts_secrets(self):
		secret = "super-secret-password"
		session = FakeSession(requests.ConnectTimeout(f"connection failed with {secret}"))
		transport = TekraSOAPTransport(settings(), session=session, secrets=(secret,))

		with self.assertRaises(SOAPTransportError) as captured:
			transport.post(soap_action="urn:certify", envelope=b"contains-secret")

		self.assertFalse(captured.exception.request_may_have_been_sent)
		self.assertNotIn(secret, str(captured.exception))
		self.assertIn("[REDACTED]", str(captured.exception))
		self.assertNotIn("contains-secret", str(captured.exception))

	def test_read_timeout_requires_reconciliation(self):
		transport = TekraSOAPTransport(settings(), session=FakeSession(requests.ReadTimeout("read timed out")))

		with self.assertRaises(SOAPTransportError) as captured:
			transport.post(soap_action="urn:certify", envelope=b"<envelope/>")

		self.assertTrue(captured.exception.request_may_have_been_sent)

	def test_rejects_declared_or_streamed_oversized_responses(self):
		for response in (
			FakeResponse([], headers={"Content-Length": "5"}),
			FakeResponse([b"123", b"45"]),
		):
			with self.subTest(headers=response.headers):
				transport = TekraSOAPTransport(settings(max_response_bytes=4), session=FakeSession(response))
				with self.assertRaises(SOAPResponseTooLarge) as captured:
					transport.post(soap_action="urn:certify", envelope=b"<envelope/>")
				self.assertTrue(captured.exception.request_may_have_been_sent)
				self.assertTrue(response.closed)
