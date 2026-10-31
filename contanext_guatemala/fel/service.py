from __future__ import annotations

from contanext_guatemala.fel.configuration import get_fel_configuration
from contanext_guatemala.fel.provider import FELProvider, UnconfiguredFELProvider, get_fel_provider
from contanext_guatemala.fel.types import (
	CancellationRequest,
	CertificationRequest,
	CertificationResult,
	ContributorQueryRequest,
	ContributorQueryResult,
	ReconciliationRequest,
)


class FELService:
	def __init__(self, provider: FELProvider | None = None) -> None:
		self.provider = provider or UnconfiguredFELProvider()

	@classmethod
	def for_company(cls, company: str) -> FELService:
		configuration = get_fel_configuration(company)
		if not configuration.enabled:
			return cls()
		return cls(provider=get_fel_provider(configuration.provider, configuration=configuration))

	def certify(self, request: CertificationRequest) -> CertificationResult:
		if not request.external_id.strip() or not request.idempotency_key.strip() or not request.xml.strip():
			raise ValueError("Documento, identificador idempotente y XML son obligatorios para certificar.")
		return self.provider.certify(request)

	def cancel(self, request: CancellationRequest) -> CertificationResult:
		if not request.uuid.strip() or not request.reason.strip() or not request.xml.strip():
			raise ValueError("UUID, motivo y XML son obligatorios para anular.")
		return self.provider.cancel(request)

	def reconcile(self, request: ReconciliationRequest) -> CertificationResult:
		if not request.idempotency_key.strip():
			raise ValueError("El identificador idempotente es obligatorio para reconciliar.")
		return self.provider.reconcile(request)

	def query_contributor(self, request: ContributorQueryRequest) -> ContributorQueryResult:
		if not request.identifier.strip() or not request.environment.strip():
			raise ValueError("Identificador y ambiente son obligatorios para consultar contribuyentes.")
		return self.provider.query_contributor(request)
