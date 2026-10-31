import frappe
from frappe.tests.utils import FrappeTestCase

from contanext_guatemala.fel.configuration import get_fel_configuration
from contanext_guatemala.fiscal.company import (
	build_company_fiscal_snapshot,
	get_company_fiscal_configuration,
	validate_company_nits,
)


class TestManualFiscalCompanyCase(FrappeTestCase):
	def test_company_and_accountant_nits_reject_invalid_syntax(self):
		for fieldname, expected_message in (
			("tax_id", "NIT de la empresa"),
			("contanext_gt_accountant_nit", "NIT del contador"),
		):
			doc = frappe.new_doc("Company")
			doc.tax_id = "1234567-8"
			doc.contanext_gt_accountant_nit = "7654321-K"
			doc.set(fieldname, "INVALID")
			with self.subTest(fieldname=fieldname), self.assertRaisesRegex(
				frappe.ValidationError, expected_message
			):
				validate_company_nits(doc)

	def test_manual_section_eight_uses_company_as_the_only_fiscal_source(self):
		company_name = "Comercializadora Quetzal, S.A."
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"name": company_name,
				"company_name": company_name,
				"abbr": "CQ",
				"country": "Guatemala",
				"default_currency": "GTQ",
				"valuation_method": "FIFO",
			}
		)
		company.db_insert()

		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": "Dirección Fiscal CQ",
				"address_type": "Billing",
				"address_line1": "10a avenida 10-10",
				"city": "Guatemala",
				"state": "Guatemala",
				"country": "Guatemala",
				"is_primary_address": 1,
				"is_your_company_address": 1,
				"links": [{"link_doctype": "Company", "link_name": company_name}],
			}
		).insert(ignore_permissions=True)

		company.reload()
		company.update(
			{
				"tax_id": " 1234567 - k ",
				"contanext_gt_trade_name": "Quetzal Escolar",
				"contanext_gt_fiscal_address": address.name,
				"contanext_gt_establishment_code": "1",
				"contanext_gt_accounting_framework": "NIIF para PYMES",
				"contanext_gt_legal_representative_name": "Representante de prueba",
				"contanext_gt_legal_representative_id": "ID-REP-CQ",
				"contanext_gt_accountant_name": "Contador de prueba",
				"contanext_gt_accountant_nit": " 7654321 - k ",
				"contanext_gt_accountant_registration": "CPA-2026",
				"contanext_gt_accountant_email": "contador.cq@example.com",
				"contanext_gt_fel_enabled": 0,
				"contanext_gt_fel_provider": None,
			}
		)
		company.save(ignore_permissions=True)

		configuration = get_company_fiscal_configuration(company_name, include_protected=True)
		self.assertEqual(configuration.legal_name, company_name)
		self.assertEqual(configuration.nit, "1234567-K")
		self.assertEqual(configuration.trade_name, "Quetzal Escolar")
		self.assertEqual(configuration.fiscal_address.address_name, address.name)
		self.assertEqual(configuration.fiscal_address.address_line1, "10a avenida 10-10")
		self.assertEqual(configuration.accounting_framework, "NIIF para PYMES")
		self.assertEqual(configuration.accountant_nit, "7654321-K")
		self.assertEqual(configuration.legal_representative_id, "ID-REP-CQ")

		settings = frappe.get_doc(
			{
				"doctype": "GT Accounting Book Settings",
				"company": company_name,
				"enabled": 1,
				"book_currency": "GTQ",
				"language": "Español",
				"time_zone": "America/Guatemala",
				"page_size": "Carta",
				"orientation_policy": "Según tipo de libro",
				"require_period_closed": 0,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(settings.company, company_name)

		fel_configuration = get_fel_configuration(company_name)
		self.assertFalse(fel_configuration.enabled)
		self.assertIsNone(fel_configuration.provider)

		snapshot = build_company_fiscal_snapshot(company_name)
		self.assertEqual(snapshot["identity"]["company"], company_name)
		self.assertEqual(snapshot["identity"]["fiscal_address"]["address_name"], address.name)
		self.assertEqual(snapshot["accountant"]["name"], "Contador de prueba")
		self.assertEqual(snapshot["representative"], {"name": "Representante de prueba"})

		self.assertFalse(frappe.db.exists("DocType", "ContaNext Tax Profile"))
		self.assertFalse(frappe.db.exists("DocType", "ContaNext Fiscal Settings"))
