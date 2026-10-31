from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

import requests

from contanext_guatemala.fel.settings import TekraEnvironmentSettings


SOAP_CONTENT_TYPE = "text/xml; charset=utf-8"
SOAP_ACCEPT = "text/xml"
RESPONSE_CHUNK_SIZE = 64 * 1024


class HTTPSession(Protocol):
	def post(self, url: str, **kwargs): ...


@dataclass(frozen=True, slots=True)
class SOAPTransportResponse:
	status_code: int
	body: bytes
	content_type: str | None = None


class SOAPTransportError(RuntimeError):
	"""A sanitized transport failure without request or credential contents."""

	def __init__(self, message: str, *, request_may_have_been_sent: bool):
		super().__init__(message)
		self.request_may_have_been_sent = request_may_have_been_sent


class SOAPResponseTooLarge(SOAPTransportError):
	pass


class TekraSOAPTransport:
	"""Bounded SOAP 1.1 HTTP transport; envelope creation and parsing live elsewhere."""

	def __init__(
		self,
		settings: TekraEnvironmentSettings,
		*,
		session: HTTPSession | None = None,
		secrets: Iterable[str] = (),
	):
		self.settings = settings
		self.session = session or requests.Session()
		self._secrets = tuple(value for value in secrets if value)

	def post(self, *, soap_action: str, envelope: bytes) -> SOAPTransportResponse:
		headers = {
			"Content-Type": SOAP_CONTENT_TYPE,
			"Accept": SOAP_ACCEPT,
			"SOAPAction": f'"{soap_action}"',
		}
		try:
			response = self.session.post(
				self.settings.endpoint,
				data=envelope,
				headers=headers,
				timeout=(
					self.settings.connect_timeout_seconds,
					self.settings.read_timeout_seconds,
				),
				allow_redirects=False,
				stream=True,
			)
		except requests.ConnectTimeout as exc:
			raise self._error("No fue posible conectar con TEKRA dentro del tiempo configurado.", exc, False) from exc
		except (requests.ReadTimeout, requests.ConnectionError) as exc:
			raise self._error("La conexión con TEKRA terminó sin una respuesta completa.", exc, True) from exc
		except requests.RequestException as exc:
			raise self._error("Falló el transporte HTTP hacia TEKRA.", exc, True) from exc

		try:
			body = self._read_bounded(response)
		except requests.RequestException as exc:
			raise self._error("La respuesta de TEKRA quedó incompleta.", exc, True) from exc
		finally:
			response.close()

		return SOAPTransportResponse(
			status_code=response.status_code,
			body=body,
			content_type=response.headers.get("Content-Type"),
		)

	def _read_bounded(self, response) -> bytes:
		content_length = response.headers.get("Content-Length")
		if content_length:
			try:
				declared_length = int(content_length)
			except ValueError:
				declared_length = 0
			if declared_length > self.settings.max_response_bytes:
				raise SOAPResponseTooLarge(
					"La respuesta de TEKRA excede el límite configurado.",
					request_may_have_been_sent=True,
				)

		body = bytearray()
		for chunk in response.iter_content(chunk_size=RESPONSE_CHUNK_SIZE):
			if not chunk:
				continue
			body.extend(chunk)
			if len(body) > self.settings.max_response_bytes:
				raise SOAPResponseTooLarge(
					"La respuesta de TEKRA excede el límite configurado.",
					request_may_have_been_sent=True,
				)
		return bytes(body)

	def _error(self, message: str, exc: Exception, request_may_have_been_sent: bool) -> SOAPTransportError:
		detail = _redact(str(exc), self._secrets)
		if detail:
			message = f"{message} Detalle sanitizado: {detail}"
		return SOAPTransportError(message, request_may_have_been_sent=request_may_have_been_sent)


def _redact(value: str, secrets: Iterable[str]) -> str:
	redacted = value
	for secret in sorted((item for item in secrets if item), key=len, reverse=True):
		redacted = redacted.replace(secret, "[REDACTED]")
	return redacted[:500]
