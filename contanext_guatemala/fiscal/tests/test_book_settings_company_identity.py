from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from contanext_guatemala.contanext_guatemala.doctype.gt_accounting_book_settings.gt_accounting_book_settings import (
	GTAccountingBookSettings,
)
from contanext_guatemala.contanext_guatemala.doctype.gt_accounting_book_run.gt_accounting_book_run import (
	GTAccountingBookRun,
)
from contanext_guatemala.books.preflight import CHECKS, check_tax_identity
from contanext_guatemala.fiscal.company import CompanyFiscalConfiguration, FiscalAddress


def company_configuration(**overrides):
	values = {
		"company": "Test Company",
		"legal_name": "Test Company, S.A.",
		"nit": "1234567-8",
		"trade_name": None,
		"fiscal_address_name": "Test Address",
		"establishment_code": "1",
		"accounting_framework": "NIIF para PYMES",
		"legal_representative_name": "Representante",
		"legal_representative_id": None,
		"accountant_name": "Contador",
		"accountant_nit": "7654321-K",
		"accountant_registration": None,
		"accountant_email": None,
		"country": "Guatemala",
		"currency": "GTQ",
		"fel_enabled": False,
		"fel_provider": None,
		"fiscal_address": object(),
	}
	values.update(overrides)
	return CompanyFiscalConfiguration(**values)


class TestBookSettingsCompanyIdentity(FrappeTestCase):
	def test_settings_metadata_has_no_tax_profile_link(self):
		meta = frappe.get_meta("GT Accounting Book Settings", cached=False)

		self.assertNotIn("tax_profile", [field.fieldname for field in meta.fields])
		self.assertFalse(
			any(
				field.fieldtype == "Link" and field.options == "ContaNext Tax Profile"
				for field in meta.fields
			)
		)

	def test_enabled_settings_require_complete_company_identity(self):
		settings = GTAccountingBookSettings(
			{"doctype": "GT Accounting Book Settings", "company": "Test Company"}
		)

		with self.assertRaisesRegex(frappe.ValidationError, "NIT, Dirección fiscal"):
			with patch(
				"contanext_guatemala.contanext_guatemala.doctype.gt_accounting_book_settings.gt_accounting_book_settings.get_company_fiscal_configuration",
				return_value=company_configuration(nit=None, fiscal_address=None),
			):
				settings._validate_company_fiscal_configuration()

	def test_enabled_settings_accept_complete_company_identity(self):
		settings = GTAccountingBookSettings(
			{"doctype": "GT Accounting Book Settings", "company": "Test Company"}
		)

		with patch(
			"contanext_guatemala.contanext_guatemala.doctype.gt_accounting_book_settings.gt_accounting_book_settings.get_company_fiscal_configuration",
			return_value=company_configuration(),
		):
			settings._validate_company_fiscal_configuration()

	def test_enabled_settings_require_guatemala_company(self):
		settings = GTAccountingBookSettings(
			{"doctype": "GT Accounting Book Settings", "company": "Foreign Company"}
		)

		with (
			patch(
				"contanext_guatemala.contanext_guatemala.doctype.gt_accounting_book_settings.gt_accounting_book_settings.get_company_fiscal_configuration",
				return_value=company_configuration(country="Canada", currency="CAD"),
			),
			self.assertRaisesRegex(frappe.ValidationError, "empresa de Guatemala"),
		):
			settings._validate_company_fiscal_configuration()

	def test_enabled_settings_require_gtq_company_currency(self):
		settings = GTAccountingBookSettings(
			{"doctype": "GT Accounting Book Settings", "company": "Test Company"}
		)

		with (
			patch(
				"contanext_guatemala.contanext_guatemala.doctype.gt_accounting_book_settings.gt_accounting_book_settings.get_company_fiscal_configuration",
				return_value=company_configuration(currency="USD"),
			),
			self.assertRaisesRegex(frappe.ValidationError, "moneda predeterminada.*GTQ"),
		):
			settings._validate_company_fiscal_configuration()

	def test_preflight_reports_complete_company_identity(self):
		with patch(
			"contanext_guatemala.books.preflight.get_company_fiscal_configuration",
			return_value=company_configuration(),
		):
			result = check_tax_identity(frappe._dict(company="Test Company"))[0]

		self.assertEqual(result.code, "GT_TAX_IDENTITY")
		self.assertEqual(result.status, "PASS")
		self.assertEqual(result.evidence["address"], "Test Address")

	def test_preflight_details_missing_and_invalid_company_identity(self):
		with patch(
			"contanext_guatemala.books.preflight.get_company_fiscal_configuration",
			return_value=company_configuration(
				nit="INVALID",
				fiscal_address=None,
				fiscal_address_name=None,
				accountant_name=None,
				currency="USD",
			),
		):
			result = check_tax_identity(frappe._dict(company="Test Company"))[0]

		self.assertEqual(result.status, "FAIL")
		self.assertEqual(result.evidence["missing_fields"], ["Dirección fiscal", "Contador"])
		self.assertEqual(result.evidence["invalid_fields"], ["NIT", "Moneda GTQ"])

	def test_preflight_has_no_fel_identity_discrepancy_check(self):
		self.assertNotIn("check_fel_discrepancy", [check.__name__ for check in CHECKS])

	def test_book_run_snapshots_use_stable_company_payloads(self):
		configuration = company_configuration(
			trade_name="Comercial Test",
			accountant_registration="CPA-1",
			accountant_email="contador@example.com",
			fiscal_address=FiscalAddress(
				address_name="Test Address",
				address_line1="1a avenida 1-01",
				address_line2=None,
				city="Guatemala",
				state="Guatemala",
				pincode="01001",
				country="Guatemala",
				display="1a avenida 1-01<br>Guatemala",
			),
		)
		run = GTAccountingBookRun(
			{"doctype": "GT Accounting Book Run", "company": "Test Company"}
		)

		with patch(
			"contanext_guatemala.fiscal.company.get_company_fiscal_configuration",
			return_value=configuration,
		):
			run._take_identity_snapshot()

		identity = frappe.parse_json(run.tax_identity_snapshot)
		accountant = frappe.parse_json(run.accountant_snapshot)
		representative = frappe.parse_json(run.representative_snapshot)
		self.assertEqual(identity["legal_name"], "Test Company, S.A.")
		self.assertEqual(identity["fiscal_address"]["pincode"], "01001")
		self.assertEqual(identity["language"], "Español")
		self.assertEqual(accountant["email"], "contador@example.com")
		self.assertEqual(representative, {"name": "Representante"})

	def test_address_changes_do_not_rewrite_existing_snapshot(self):
		suffix = frappe.generate_hash(length=6).upper()
		company_name = f"Snapshot Company {suffix}"
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"name": company_name,
				"company_name": company_name,
				"abbr": f"S{suffix[:4]}",
				"country": "Guatemala",
				"default_currency": "GTQ",
			}
		)
		company.db_insert()
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": company_name,
				"address_type": "Billing",
				"address_line1": "Dirección original",
				"address_line2": "Nivel 2",
				"city": "Guatemala",
				"state": "Guatemala",
				"pincode": "01001",
				"country": "Guatemala",
				"is_your_company_address": 1,
				"links": [{"link_doctype": "Company", "link_name": company_name}],
			}
		).insert(ignore_permissions=True)
		company.db_set("contanext_gt_fiscal_address", address.name, update_modified=False)

		run = GTAccountingBookRun(
			{"doctype": "GT Accounting Book Run", "company": company_name}
		)
		run._take_identity_snapshot()
		original_snapshot = run.tax_identity_snapshot
		original_address = frappe.parse_json(original_snapshot)["fiscal_address"]

		address.db_set("address_line1", "Dirección modificada", update_modified=False)

		self.assertEqual(run.tax_identity_snapshot, original_snapshot)
		self.assertEqual(original_address["address_line1"], "Dirección original")
		self.assertEqual(
			set(original_address),
			{
				"address_name",
				"address_line1",
				"address_line2",
				"city",
				"state",
				"pincode",
				"country",
				"display",
			},
		)

	def test_active_fiscal_address_cannot_be_deleted_while_company_uses_it(self):
		suffix = frappe.generate_hash(length=6).upper()
		company_name = f"Address Guard Company {suffix}"
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"name": company_name,
				"company_name": company_name,
				"abbr": f"A{suffix[:4]}",
				"country": "Guatemala",
				"default_currency": "GTQ",
			}
		)
		company.db_insert()
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": company_name,
				"address_type": "Billing",
				"address_line1": "Dirección protegida",
				"city": "Guatemala",
				"country": "Guatemala",
				"is_your_company_address": 1,
				"links": [{"link_doctype": "Company", "link_name": company_name}],
			}
		).insert(ignore_permissions=True)
		company.db_set("contanext_gt_fiscal_address", address.name, update_modified=False)

		with self.assertRaises(frappe.LinkExistsError):
			address.delete(ignore_permissions=True)

		self.assertTrue(frappe.db.exists("Address", address.name))
		self.assertEqual(
			frappe.db.get_value("Company", company_name, "contanext_gt_fiscal_address"),
			address.name,
		)
