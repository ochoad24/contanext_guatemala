from dataclasses import FrozenInstanceError
from unittest import TestCase
from unittest.mock import Mock, patch

from contanext_guatemala.fiscal.company import (
	CompanyFiscalConfiguration,
	FiscalAddress,
	get_company_fiscal_configuration,
)


class TestCompanyFiscalConfigurationResolver(TestCase):
	def _company_doc(self):
		values = {
			"contanext_gt_trade_name": "Comercial A",
			"contanext_gt_fiscal_address": "Dirección A",
			"contanext_gt_establishment_code": "1",
			"contanext_gt_accounting_framework": "NIIF",
			"contanext_gt_legal_representative_name": "Representante A",
			"contanext_gt_accountant_name": "Contador A",
			"contanext_gt_accountant_nit": "9876543-2",
			"contanext_gt_accountant_registration": "CPA-1",
			"contanext_gt_accountant_email": "contador@example.com",
			"contanext_gt_fel_enabled": 1,
			"contanext_gt_fel_provider": "provider-a",
		}
		doc = Mock()
		doc.name = "Company A"
		doc.company_name = "Company A, S.A."
		doc.tax_id = "1234567-8"
		doc.country = "Guatemala"
		doc.default_currency = "GTQ"
		doc.get.side_effect = values.get
		doc.get_password.return_value = "protected-id"
		return doc

	def _address(self):
		return FiscalAddress(
			address_name="Dirección A",
			address_line1="Avenida Reforma 1-01",
			address_line2=None,
			city="Guatemala",
			state="Guatemala",
			pincode="01010",
			country="Guatemala",
			display="Avenida Reforma 1-01, Guatemala",
		)

	def test_resolves_native_and_custom_company_fields_without_exposing_protected_id(self):
		doc = self._company_doc()
		address = self._address()
		with (
			patch("contanext_guatemala.fiscal.company.frappe.get_doc", return_value=doc) as get_doc,
			patch(
				"contanext_guatemala.fiscal.company.get_company_fiscal_address",
				return_value=address,
			) as get_address,
		):
			configuration = get_company_fiscal_configuration("Company A")

		get_doc.assert_called_once_with("Company", "Company A")
		get_address.assert_called_once_with("Company A")
		doc.get_password.assert_not_called()
		self.assertEqual(configuration.company, "Company A")
		self.assertEqual(configuration.legal_name, "Company A, S.A.")
		self.assertEqual(configuration.nit, "1234567-8")
		self.assertEqual(configuration.currency, "GTQ")
		self.assertTrue(configuration.fel_enabled)
		self.assertIs(configuration.fiscal_address, address)
		self.assertIsNone(configuration.legal_representative_id)

	def test_includes_protected_id_only_when_explicitly_requested(self):
		doc = self._company_doc()
		with (
			patch("contanext_guatemala.fiscal.company.frappe.get_doc", return_value=doc),
			patch("contanext_guatemala.fiscal.company.get_company_fiscal_address", return_value=None),
		):
			configuration = get_company_fiscal_configuration("Company A", include_protected=True)

		doc.get_password.assert_called_once_with(
			"contanext_gt_legal_representative_id", raise_exception=False
		)
		self.assertEqual(configuration.legal_representative_id, "protected-id")

	def test_returns_immutable_configuration_and_address_dtos(self):
		configuration = CompanyFiscalConfiguration(
			company="Company A",
			legal_name="Company A, S.A.",
			nit="1234567-8",
			trade_name=None,
			fiscal_address_name="Dirección A",
			establishment_code="1",
			accounting_framework="NIIF",
			legal_representative_name=None,
			legal_representative_id=None,
			accountant_name=None,
			accountant_nit=None,
			accountant_registration=None,
			accountant_email=None,
			country="Guatemala",
			currency="GTQ",
			fel_enabled=False,
			fel_provider=None,
			fiscal_address=self._address(),
		)

		with self.assertRaises(FrozenInstanceError):
			configuration.nit = "other"
		with self.assertRaises(FrozenInstanceError):
			configuration.fiscal_address.city = "Other"
