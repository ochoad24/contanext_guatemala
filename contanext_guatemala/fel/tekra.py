from __future__ import annotations

from typing import Any

from contanext_guatemala.fel.classification import (
	result_from_exception,
	result_from_extracted,
	result_from_http_error,
)
from contanext_guatemala.fel.provider import FELProvider, FELProviderPermanentError
from contanext_guatemala.fel.result import extract_tekra_result
from contanext_guatemala.fel.settings import validate_tekra_environment
from contanext_guatemala.fel.soap import (
	TekraSOAPCredentials,
	build_cancellation_envelope,
	build_certification_envelope,
	parse_soap_response,
)
from contanext_guatemala.fel.transport import TekraSOAPTransport
from contanext_guatemala.fel.types import (
	CancellationRequest,
	CertificationRequest,
	CertificationResult,
	ContributorQueryRequest,
	ContributorQueryResult,
	ReconciliationRequest,
)


class TekraFELProvider(FELProvider):
	def __init__(self, configuration: Any = None, *, environ: dict[str, str] | None = None, session=None):
		self.configuration = configuration
		self.environ = environ
		self.session = session

	@classmethod
	def from_configuration(cls, configuration: Any = None) -> "TekraFELProvider":
		return cls(configuration=configuration)

	def certify(self, request: CertificationRequest) -> CertificationResult:
		return self._execute(request, cancellation=False)

	def cancel(self, request: CancellationRequest) -> CertificationResult:
		return self._execute(request, cancellation=True)

	def reconcile(self, request: ReconciliationRequest) -> CertificationResult:
		raise FELProviderPermanentError(
			"TEKRA no tiene recuperación automática homologada; la operación requiere reconciliación manual."
		)

	def query_contributor(self, request: ContributorQueryRequest) -> ContributorQueryResult:
		raise FELProviderPermanentError("La consulta de contribuyentes TEKRA se implementará en la Fase 10.")

	def _execute(
		self,
		request: CertificationRequest | CancellationRequest,
		*,
		cancellation: bool,
	) -> CertificationResult:
		raw_response = None
		http_status = None
		try:
			settings = validate_tekra_environment(self._environment(), environ=self.environ)
			credentials = TekraSOAPCredentials(
				user=settings.user,
				password=settings.password,
				client=settings.client,
				contract=settings.contract,
				origin_id=self._origin_id(),
				origin_ip=self._origin_ip(request),
				sign_issuer=self._sign_issuer(),
			)
			if cancellation:
				envelope = build_cancellation_envelope(credentials, request.xml)
				soap_action = settings.cancel_soap_action
			else:
				envelope = build_certification_envelope(credentials, request.xml)
				soap_action = settings.certify_soap_action
			transport = TekraSOAPTransport(
				settings,
				session=self.session,
				secrets=(settings.user, settings.password, settings.client, settings.contract),
			)
			response = transport.post(soap_action=soap_action, envelope=envelope)
			raw_response = response.body
			http_status = response.status_code
			if not 200 <= response.status_code < 300:
				return result_from_http_error(response.status_code, raw_response=response.body)
			parsed = parse_soap_response(response.body)
			extracted = extract_tekra_result(parsed)
			return result_from_extracted(extracted, http_status=response.status_code, raw_response=response.body)
		except Exception as exc:
			return result_from_exception(exc, http_status=http_status, raw_response=raw_response)

	def _environment(self) -> str:
		return getattr(self.configuration, "environment", None) or "SANDBOX"

	def _origin_id(self) -> str:
		return getattr(self.configuration, "origin_id", None) or ""

	def _sign_issuer(self) -> bool:
		return bool(getattr(self.configuration, "sign_issuer", True))

	def _origin_ip(self, request: CertificationRequest | CancellationRequest) -> str:
		return str(request.metadata.get("origin_ip", "")).strip()
