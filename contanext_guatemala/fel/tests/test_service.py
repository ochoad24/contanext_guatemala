from unittest.mock import patch

from frappe.tests.utils import FrappeTestCase

from contanext_guatemala.fel.configuration import FELConfiguration
from contanext_guatemala.fel.provider import (
	FEL_PROVIDER_REGISTRY,
	FELProvider,
	FELProviderNotConfigured,
	UnconfiguredFELProvider,
)
from contanext_guatemala.fel.service import FELService
from contanext_guatemala.fel.types import CertificationRequest, CertificationResult, FELStatus
from contanext_guatemala.fel.types import (
	CancellationRequest,
	ContributorQueryRequest,
	ContributorQueryResult,
	DTEType,
	IdentificationType,
	ReconciliationRequest,
)


class CompanyAProvider(FELProvider):
	def certify(self, request: CertificationRequest) -> CertificationResult:
		return CertificationResult(status=FELStatus.CERTIFIED)

	def cancel(self, request: CancellationRequest) -> CertificationResult:
		return CertificationResult(status=FELStatus.CANCELLED)

	def reconcile(self, request: ReconciliationRequest) -> CertificationResult:
		return CertificationResult(status=FELStatus.CERTIFIED)

	def query_contributor(self, request: ContributorQueryRequest) -> ContributorQueryResult:
		return ContributorQueryResult(status="VALID")


class CompanyBProvider(CompanyAProvider):
	pass


class TestFELServiceCompanyProvider(FrappeTestCase):
	def _configuration(self, company: str, provider: str | None, *, enabled: bool = True):
		return FELConfiguration(
			company=company,
			enabled=enabled,
			provider=provider,
			legal_name=f"{company}, S.A.",
			nit="1234567-8",
			trade_name=None,
			establishment_code="1",
			fiscal_address=None,
		)

	def test_builds_service_with_provider_from_requested_company(self):
		configurations = {
			"Company A": self._configuration("Company A", "provider-a"),
			"Company B": self._configuration("Company B", "provider-b"),
		}
		with (
			patch(
				"contanext_guatemala.fel.service.get_fel_configuration",
				side_effect=configurations.__getitem__,
			) as resolver,
			patch.dict(
				FEL_PROVIDER_REGISTRY,
				{"provider-a": CompanyAProvider, "provider-b": CompanyBProvider},
				clear=True,
			),
		):
			service = FELService.for_company("Company A")

		resolver.assert_called_once_with("Company A")
		self.assertIsInstance(service.provider, CompanyAProvider)
		self.assertNotIsInstance(service.provider, CompanyBProvider)

	def test_disabled_company_does_not_instantiate_configured_provider(self):
		configuration = self._configuration("Company A", "provider-a", enabled=False)
		with (
			patch(
				"contanext_guatemala.fel.service.get_fel_configuration",
				return_value=configuration,
			),
			patch.dict(FEL_PROVIDER_REGISTRY, {"provider-a": CompanyAProvider}, clear=True),
		):
			service = FELService.for_company("Company A")

		self.assertIsInstance(service.provider, UnconfiguredFELProvider)

	def test_default_service_fails_closed_instead_of_simulating_certification(self):
		service = FELService()
		request = CertificationRequest(
			document_type=DTEType.FACT,
			external_id="INV-1",
			idempotency_key="Company A::Sales Invoice::INV-1",
			xml=b"<dte />",
		)

		operations = (
			lambda: service.certify(request),
			lambda: service.cancel(CancellationRequest(uuid="uuid", reason="reason", xml=b"<cancel />")),
			lambda: service.reconcile(ReconciliationRequest(idempotency_key="stable-id")),
			lambda: service.query_contributor(
				ContributorQueryRequest(
					identification_type=IdentificationType.NIT,
					identifier="1234567-8",
					environment="SANDBOX",
				)
			),
		)
		for operation in operations:
			with self.subTest(operation=operation), self.assertRaises(FELProviderNotConfigured):
				operation()

	def test_package_exports_service_without_eager_import_cycle(self):
		from contanext_guatemala.fel import FELService as ExportedFELService

		self.assertIs(ExportedFELService, FELService)

	def test_disabled_company_service_fails_closed_for_certification(self):
		configuration = self._configuration("Company A", "provider-a", enabled=False)
		with (
			patch(
				"contanext_guatemala.fel.service.get_fel_configuration",
				return_value=configuration,
			),
			patch.dict(FEL_PROVIDER_REGISTRY, {"provider-a": CompanyAProvider}, clear=True),
		):
			service = FELService.for_company("Company A")

		request = CertificationRequest(
			document_type=DTEType.FACT,
			external_id="INV-1",
			idempotency_key="Company A::Sales Invoice::INV-1",
			xml=b"<dte />",
		)
		with self.assertRaises(FELProviderNotConfigured):
			service.certify(request)
