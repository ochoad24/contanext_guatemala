from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from contanext_guatemala.fel.provider import (
	FEL_PROVIDER_REGISTRY,
	FELProviderNotConfigured,
	UnconfiguredFELProvider,
)
from contanext_guatemala.fel.types import (
	CancellationRequest,
	CertificationRequest,
	ContributorQueryRequest,
	DTEType,
	IdentificationType,
	ReconciliationRequest,
)
from contanext_guatemala.fiscal.company import validate_company_fiscal_configuration


class TestCompanyFELActivation(FrappeTestCase):
	def _company(self, **overrides):
		company = frappe._dict(
			country="Guatemala",
			name="FEL Test Company",
			company_name="FEL Test Company, S.A.",
			tax_id="1234567-8",
			contanext_gt_fiscal_address="FEL Test Address",
			contanext_gt_establishment_code="1",
			contanext_gt_fel_enabled=1,
			contanext_gt_fel_provider="test-provider",
		)
		company.update(overrides)
		return company

	def _validate(self, company):
		with (
			patch("contanext_guatemala.fiscal.company.validate_company_fiscal_changes"),
			patch("contanext_guatemala.fiscal.company.validate_company_fiscal_address"),
		):
			validate_company_fiscal_configuration(company)

	def test_disabled_fel_does_not_require_identity_or_provider(self):
		self._validate(
			self._company(
				company_name="",
				tax_id="",
				contanext_gt_fiscal_address="",
				contanext_gt_establishment_code="",
				contanext_gt_fel_enabled=0,
				contanext_gt_fel_provider="",
			)
		)

	def test_enabled_fel_requires_complete_identity(self):
		company = self._company(
			tax_id="",
			contanext_gt_fiscal_address="",
			contanext_gt_establishment_code="",
			contanext_gt_fel_provider="",
		)

		with self.assertRaisesRegex(
			frappe.ValidationError,
			"NIT.*Dirección fiscal.*Código de establecimiento fiscal.*Adaptador de certificador",
		):
			self._validate(company)

	def test_enabled_fel_rejects_invalid_company_nit(self):
		with self.assertRaisesRegex(frappe.ValidationError, "NIT.*formato inválido"):
			self._validate(self._company(tax_id="NIT-INVALIDO"))

	def test_enabled_fel_rejects_unregistered_provider(self):
		with self.assertRaisesRegex(frappe.ValidationError, "adaptador.*no está registrado"):
			self._validate(self._company())

	def test_enabled_fel_accepts_registered_provider_and_normalizes_values(self):
		company = self._company(tax_id=" 1234567-k ", contanext_gt_fel_provider=" test-provider ")

		with patch.dict(
			FEL_PROVIDER_REGISTRY,
			{"test-provider": UnconfiguredFELProvider},
			clear=True,
		):
			self._validate(company)

		self.assertEqual(company.tax_id, "1234567-K")
		self.assertEqual(company.contanext_gt_fel_provider, "test-provider")

	def test_unconfigured_provider_fails_closed_for_every_operation(self):
		provider = UnconfiguredFELProvider()
		request = CertificationRequest(
			document_type=DTEType.FACT,
			external_id="INV-1",
			idempotency_key="Company A::Sales Invoice::INV-1",
			xml=b"<dte />",
		)

		operations = (
			lambda: provider.certify(request),
			lambda: provider.cancel(CancellationRequest(uuid="uuid", reason="reason", xml=b"<cancel />")),
			lambda: provider.reconcile(ReconciliationRequest(idempotency_key="stable-id")),
			lambda: provider.query_contributor(
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
