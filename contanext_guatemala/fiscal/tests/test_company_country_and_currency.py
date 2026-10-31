import frappe
from frappe.tests.utils import FrappeTestCase

from contanext_guatemala.fiscal.company import validate_company_fiscal_configuration


class TestCompanyCountryAndCurrencyValidation(FrappeTestCase):
	def test_guatemala_company_can_start_without_complete_fiscal_configuration(self):
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": f"GT Initial Fiscal {frappe.generate_hash(length=6)}",
				"abbr": frappe.generate_hash(length=5).upper(),
				"country": "Guatemala",
				"default_currency": "GTQ",
			}
		)

		company.run_method("validate")

		self.assertFalse(company.tax_id)
		self.assertFalse(company.contanext_gt_fiscal_address)
		self.assertFalse(company.contanext_gt_accounting_framework)

	def test_guatemala_company_creation_does_not_require_gtq(self):
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": f"GT Initial Currency {frappe.generate_hash(length=6)}",
				"abbr": frappe.generate_hash(length=5).upper(),
				"country": "Guatemala",
				"default_currency": "USD",
			}
		)

		company.run_method("validate")

		self.assertEqual(company.default_currency, "USD")

	def test_company_from_another_country_can_be_saved_without_gt_configuration(self):
		company = frappe._dict(country="Canada")

		validate_company_fiscal_configuration(company)

	def test_company_from_another_country_rejects_gt_configuration(self):
		company = frappe._dict(
			country="Canada",
			contanext_gt_trade_name="Nombre comercial GT",
		)

		with self.assertRaisesRegex(frappe.ValidationError, "solo puede usarse.*Guatemala"):
			validate_company_fiscal_configuration(company)
