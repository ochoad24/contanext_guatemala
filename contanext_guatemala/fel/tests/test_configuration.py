from dataclasses import FrozenInstanceError
from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from contanext_guatemala.fel.configuration import FELConfiguration, get_fel_configuration
from contanext_guatemala.fel.provider import FEL_PROVIDER_REGISTRY, UnconfiguredFELProvider
from contanext_guatemala.fiscal.company import CompanyFiscalConfiguration, FiscalAddress


class TestFELConfiguration(FrappeTestCase):
	def _company_configuration(self, company="Company A", **overrides):
		values = {
			"company": company,
			"legal_name": f"{company}, S.A.",
			"nit": "1234567-8",
			"trade_name": f"Trade {company}",
			"fiscal_address_name": f"Address {company}",
			"establishment_code": "1",
			"accounting_framework": "NIIF",
			"legal_representative_name": "Representative",
			"legal_representative_id": None,
			"accountant_name": "Accountant",
			"accountant_nit": "9876543-2",
			"accountant_registration": "CPA-1",
			"accountant_email": "accountant@example.com",
			"country": "Guatemala",
			"currency": "GTQ",
			"fel_enabled": True,
			"fel_provider": "test-provider",
			"fel_policy": "ALWAYS",
			"vat_affiliation": "GEN",
			"price_tax_mode": "TAX_INCLUDED",
			"tekra_environment": "SANDBOX",
			"tekra_origin_id": "origin-a",
			"tekra_sign_issuer": True,
			"default_establishment": "GT-FEL-EST-1",
			"fel_phrases": ({"phrase_type": 1, "scenario_code": 1},),
			"fiscal_address": FiscalAddress(
				address_name=f"Address {company}",
				address_line1=f"Street {company}",
				address_line2=None,
				city="Guatemala",
				state="Guatemala",
				pincode="01001",
				country="Guatemala",
				display=f"Street {company}, Guatemala",
			),
		}
		values.update(overrides)
		return CompanyFiscalConfiguration(**values)

	def test_resolves_only_the_requested_company(self):
		configurations = {
			"Company A": self._company_configuration("Company A"),
			"Company B": self._company_configuration("Company B"),
		}

		with (
			patch(
				"contanext_guatemala.fel.configuration.get_company_fiscal_configuration",
				side_effect=configurations.__getitem__,
			) as resolver,
			patch.dict(FEL_PROVIDER_REGISTRY, {"test-provider": UnconfiguredFELProvider}, clear=True),
		):
			configuration = get_fel_configuration("Company A")

		resolver.assert_called_once_with("Company A")
		self.assertEqual(configuration.company, "Company A")
		self.assertEqual(configuration.legal_name, "Company A, S.A.")
		self.assertEqual(configuration.trade_name, "Trade Company A")
		self.assertEqual(configuration.fiscal_address.address_line1, "Street Company A")
		self.assertNotIn("Company B", repr(configuration))

	def test_disabled_company_returns_configuration_without_requiring_identity_or_provider(self):
		company_configuration = self._company_configuration(
			fel_enabled=False,
			legal_name="",
			nit=None,
			fiscal_address_name=None,
			establishment_code=None,
			fel_provider=None,
			fiscal_address=None,
		)

		with patch(
			"contanext_guatemala.fel.configuration.get_company_fiscal_configuration",
			return_value=company_configuration,
		):
			configuration = get_fel_configuration("Company A")

		self.assertFalse(configuration.enabled)
		self.assertIsNone(configuration.provider)

	def test_enabled_company_requires_complete_fel_identity(self):
		company_configuration = self._company_configuration(
			nit=None,
			fiscal_address_name=None,
			establishment_code=None,
			fel_provider=None,
			fiscal_address=None,
		)

		with (
			patch(
				"contanext_guatemala.fel.configuration.get_company_fiscal_configuration",
				return_value=company_configuration,
			),
			self.assertRaisesRegex(
				frappe.ValidationError,
				"NIT.*Dirección fiscal.*Código de establecimiento fiscal.*Adaptador de certificador",
			),
		):
			get_fel_configuration("Company A")

	def test_enabled_company_rejects_invalid_nit(self):
		with (
			patch(
				"contanext_guatemala.fel.configuration.get_company_fiscal_configuration",
				return_value=self._company_configuration(nit="INVALID"),
			),
			patch.dict(FEL_PROVIDER_REGISTRY, {"test-provider": UnconfiguredFELProvider}, clear=True),
			self.assertRaisesRegex(frappe.ValidationError, "NIT inválido"),
		):
			get_fel_configuration("Company A")

	def test_enabled_company_rejects_unregistered_provider(self):
		with (
			patch(
				"contanext_guatemala.fel.configuration.get_company_fiscal_configuration",
				return_value=self._company_configuration(),
			),
			patch.dict(FEL_PROVIDER_REGISTRY, {}, clear=True),
			self.assertRaisesRegex(frappe.ValidationError, "adaptador FEL.*no está registrado"),
		):
			get_fel_configuration("Company A")

	def test_enabled_company_returns_normalized_immutable_configuration(self):
		with (
			patch(
				"contanext_guatemala.fel.configuration.get_company_fiscal_configuration",
				return_value=self._company_configuration(
					nit=" 1234567-k ", fel_provider=" test-provider "
				),
			),
			patch.dict(FEL_PROVIDER_REGISTRY, {"test-provider": UnconfiguredFELProvider}, clear=True),
		):
			configuration = get_fel_configuration("Company A")

		self.assertEqual(configuration.nit, "1234567-K")
		self.assertEqual(configuration.provider, "test-provider")
		self.assertEqual(configuration.policy, "ALWAYS")
		self.assertEqual(configuration.default_establishment, "GT-FEL-EST-1")
		self.assertEqual(configuration.phrases[0]["phrase_type"], 1)
		with self.assertRaises(FrozenInstanceError):
			configuration.provider = "other-provider"
		self.assertIsInstance(configuration, FELConfiguration)
