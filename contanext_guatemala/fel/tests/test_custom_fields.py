import frappe
from frappe.tests.utils import FrappeTestCase

from contanext_guatemala.fiscal.setup import (
	get_company_fiscal_custom_fields,
	get_fel_master_and_transaction_custom_fields,
	install_company_fiscal_custom_fields,
)


class TestFELCustomFields(FrappeTestCase):
	def test_definitions_cover_all_required_doctypes(self):
		definitions = get_fel_master_and_transaction_custom_fields()
		self.assertEqual(set(definitions), {"Customer", "Item", "Sales Invoice", "POS Invoice"})
		company = {field["fieldname"]: field for field in get_company_fiscal_custom_fields()["Company"]}
		self.assertEqual(company["contanext_gt_default_establishment"]["options"], "GT FEL Establishment")

	def test_customer_item_and_sales_fields_are_explicit(self):
		definitions = get_fel_master_and_transaction_custom_fields()
		customer = {field["fieldname"]: field for field in definitions["Customer"]}
		item = {field["fieldname"]: field for field in definitions["Item"]}
		sales = {field["fieldname"]: field for field in definitions["Sales Invoice"]}

		self.assertIn("EXT", customer["contanext_gt_identification_type"]["options"])
		self.assertEqual(item["contanext_gt_fel_item_kind"]["options"], "\nB\nS")
		self.assertEqual(sales["contanext_gt_fel_establishment"]["options"], "GT FEL Establishment")
		self.assertEqual(sales["contanext_gt_fel_operation"]["options"], "FEL Operation")
		self.assertEqual(sales["contanext_gt_fel_uuid"]["read_only"], 1)

	def test_installation_is_idempotent_and_metadata_is_available(self):
		install_company_fiscal_custom_fields()
		install_company_fiscal_custom_fields()

		for doctype, fieldname in (
			("Company", "contanext_gt_default_establishment"),
			("Customer", "contanext_gt_identification_type"),
			("Item", "contanext_gt_fel_item_kind"),
			("Sales Invoice", "contanext_gt_fel_operation"),
			("POS Invoice", "contanext_gt_fel_operation"),
		):
			with self.subTest(doctype=doctype, fieldname=fieldname):
				self.assertIsNotNone(frappe.get_meta(doctype, cached=False).get_field(fieldname))
