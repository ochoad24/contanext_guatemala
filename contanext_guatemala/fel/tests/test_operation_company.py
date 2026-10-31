import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase


FEL_OPERATION_DEFINITION = (
	Path(__file__).parents[2]
	/ "contanext_guatemala"
	/ "doctype"
	/ "fel_operation"
	/ "fel_operation.json"
)


class TestFELOperationCompany(FrappeTestCase):
	def _company(self, marker):
		suffix = frappe.generate_hash(length=6).upper()
		company_name = f"FEL Operation {marker} {suffix}"
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"name": company_name,
				"company_name": company_name,
				"abbr": f"{marker}{suffix[:4]}",
				"country": "Guatemala",
				"default_currency": "GTQ",
			}
		)
		company.db_insert()
		return company

	def _operation(self, company, source_doctype="Company", source_name=None):
		return frappe.get_doc(
			{
				"doctype": "FEL Operation",
				"company": company,
				"document_type": "FACT",
				"source_doctype": source_doctype,
				"source_name": source_name or company,
				"operation": "CERTIFY",
				"status": "PENDING",
				"idempotency_key": f"{company}::{source_doctype}::{source_name or company}::{frappe.generate_hash(length=8)}",
			}
		)

	def test_definition_requires_company_link_before_document_identity(self):
		definition = json.loads(FEL_OPERATION_DEFINITION.read_text())
		company_field = next(
			field for field in definition["fields"] if field["fieldname"] == "company"
		)

		self.assertEqual(company_field["fieldtype"], "Link")
		self.assertEqual(company_field["options"], "Company")
		self.assertEqual(company_field["reqd"], 1)
		self.assertEqual(company_field["in_list_view"], 1)
		self.assertLess(
			definition["field_order"].index("company"),
			definition["field_order"].index("source_doctype"),
		)

	def test_installed_metadata_and_document_persist_company(self):
		meta = frappe.get_meta("FEL Operation", cached=False)
		company_field = meta.get_field("company")

		self.assertIsNotNone(company_field)
		self.assertEqual(company_field.fieldtype, "Link")
		self.assertEqual(company_field.options, "Company")
		self.assertTrue(company_field.reqd)

		company = frappe.get_all("Company", pluck="name", limit=1)[0]
		operation = frappe.get_doc(
			{
				"doctype": "FEL Operation",
				"company": company,
				"document_type": "FACT",
				"source_doctype": "Company",
				"source_name": company,
				"operation": "CERTIFY",
				"status": "PENDING",
				"idempotency_key": f"{company}::Company::{company}::{frappe.generate_hash(length=8)}",
			}
		).insert(ignore_permissions=True)

		operation.reload()
		self.assertEqual(operation.company, company)

		queried_operation = frappe.get_value(
			"FEL Operation",
			operation.name,
			("name", "company", "source_doctype", "source_name"),
			as_dict=True,
		)
		self.assertEqual(queried_operation.company, company)
		self.assertEqual(queried_operation.source_doctype, "Company")
		self.assertEqual(queried_operation.source_name, company)

	def test_company_is_required_by_frappe(self):
		company = frappe.get_all("Company", pluck="name", limit=1)[0]
		operation = frappe.get_doc(
			{
				"doctype": "FEL Operation",
				"document_type": "FACT",
				"source_doctype": "Company",
				"source_name": company,
				"operation": "CERTIFY",
				"status": "PENDING",
				"idempotency_key": f"missing-company::{frappe.generate_hash(length=8)}",
			}
		)

		with self.assertRaises(frappe.MandatoryError):
			operation.insert(ignore_permissions=True)

	def test_source_document_from_same_company_is_accepted(self):
		company = self._company("A")

		operation = self._operation(company.name).insert(ignore_permissions=True)

		self.assertEqual(operation.company, company.name)
		self.assertEqual(operation.source_name, company.name)

	def test_source_document_from_another_company_is_rejected(self):
		operation_company = self._company("A")
		source_company = self._company("B")

		with self.assertRaisesRegex(
			frappe.ValidationError,
			"pertenece a la empresa.*no a la empresa.*operación FEL",
		):
			self._operation(
				operation_company.name,
				source_name=source_company.name,
			).insert(ignore_permissions=True)

	def test_source_document_without_company_is_rejected(self):
		company = self._company("A")

		with self.assertRaisesRegex(
			frappe.ValidationError,
			"documento origen.*no define una empresa",
		):
			self._operation(
				company.name,
				source_doctype="User",
				source_name="Administrator",
			).insert(ignore_permissions=True)
