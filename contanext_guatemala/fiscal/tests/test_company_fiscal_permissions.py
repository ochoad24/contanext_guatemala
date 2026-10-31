from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.permissions import add_user_permission

from contanext_guatemala.fiscal.company import (
	COMPANY_FISCAL_EDITOR_ROLES,
	COMPANY_FISCAL_PROTECTED_FIELDS,
	validate_company_fiscal_changes,
)


class TestCompanyFiscalServerPermissions(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.company_name = frappe.get_all("Company", pluck="name", limit=1)[0]
		frappe.db.set_value("Company", self.company_name, "country", "Guatemala")

	def test_protected_fields_cover_native_identity_and_gt_configuration(self):
		self.assertEqual(COMPANY_FISCAL_EDITOR_ROLES, {"System Manager", "GT Books Manager"})
		self.assertIn("company_name", COMPANY_FISCAL_PROTECTED_FIELDS)
		self.assertIn("tax_id", COMPANY_FISCAL_PROTECTED_FIELDS)
		self.assertIn("contanext_gt_trade_name", COMPANY_FISCAL_PROTECTED_FIELDS)
		self.assertIn("contanext_gt_legal_representative_id", COMPANY_FISCAL_PROTECTED_FIELDS)
		self.assertIn("contanext_gt_fel_provider", COMPANY_FISCAL_PROTECTED_FIELDS)

	def test_accounts_manager_api_cannot_change_native_or_custom_fiscal_fields(self):
		original_tax_id = frappe.db.get_value("Company", self.company_name, "tax_id")
		original_trade_name = frappe.db.get_value(
			"Company", self.company_name, "contanext_gt_trade_name"
		)

		for fieldname, value in (
			("tax_id", "1234567-8"),
			("contanext_gt_trade_name", "Cambio no autorizado"),
		):
			with self.subTest(fieldname=fieldname):
				company = frappe.get_doc("Company", self.company_name)
				company.set(fieldname, value)
				with (
					patch("frappe.get_roles", return_value=["Accounts Manager"]),
					self.assertRaisesRegex(
						frappe.PermissionError,
						"Solo System Manager o GT Books Manager",
					),
				):
					company.save(ignore_permissions=True)

		self.assertEqual(
			frappe.db.get_value("Company", self.company_name, "tax_id"), original_tax_id
		)
		self.assertEqual(
			frappe.db.get_value("Company", self.company_name, "contanext_gt_trade_name"),
			original_trade_name,
		)

	def test_approved_roles_can_change_a_fiscal_field_through_the_api(self):
		for role in ("System Manager", "GT Books Manager"):
			with self.subTest(role=role):
				company = frappe.get_doc("Company", self.company_name)
				expected = f"Cambio autorizado por {role}"
				company.contanext_gt_trade_name = expected

				with patch("frappe.get_roles", return_value=[role]):
					company.save(ignore_permissions=True)

				self.assertEqual(
					frappe.db.get_value(
						"Company", self.company_name, "contanext_gt_trade_name"
					),
					expected,
				)

	def test_gt_fel_manager_can_change_only_fel_configuration_fields(self):
		company = frappe.get_doc("Company", self.company_name)
		company.contanext_gt_fel_policy = "ASK_EACH_TIME"
		with patch("frappe.get_roles", return_value=["GT FEL Manager"]):
			company.save(ignore_permissions=True)

		company = frappe.get_doc("Company", self.company_name)
		company.contanext_gt_trade_name = "No autorizado para FEL Manager"
		with (
			patch("frappe.get_roles", return_value=["GT FEL Manager"]),
			self.assertRaises(frappe.PermissionError),
		):
			company.save(ignore_permissions=True)

	def test_gt_books_manager_remains_restricted_by_company_user_permission(self):
		suffix = frappe.generate_hash(length=6).upper()
		companies = []
		for marker in ("A", "B"):
			company_name = f"Fiscal Permission {marker} {suffix}"
			frappe.get_doc(
				{
					"doctype": "Company",
					"name": company_name,
					"company_name": company_name,
					"abbr": f"F{marker}{suffix[:3]}",
					"country": "Guatemala",
					"default_currency": "GTQ",
					"valuation_method": "FIFO",
				}
			).db_insert()
			companies.append(company_name)

		email = f"fiscal-manager-{suffix.lower()}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Fiscal Manager Test",
				"enabled": 1,
				"send_welcome_email": 0,
				"roles": [{"role": "GT Books Manager"}],
			}
		).insert(ignore_permissions=True)
		add_user_permission("Company", companies[0], email)

		self.assertTrue(frappe.has_permission("Company", "write", companies[0], email))
		self.assertFalse(frappe.has_permission("Company", "write", companies[1], email))

		previous_user = frappe.session.user
		try:
			frappe.set_user(email)
			allowed = frappe.get_doc("Company", companies[0])
			allowed.contanext_gt_trade_name = "Cambio permitido"
			allowed.save()

			denied = frappe.get_doc("Company", companies[1])
			denied.contanext_gt_trade_name = "Cambio denegado"
			with self.assertRaises(frappe.PermissionError):
				denied.save()
		finally:
			frappe.set_user(previous_user)

		self.assertEqual(
			frappe.db.get_value("Company", companies[0], "contanext_gt_trade_name"),
			"Cambio permitido",
		)
		self.assertNotEqual(
			frappe.db.get_value("Company", companies[1], "contanext_gt_trade_name"),
			"Cambio denegado",
		)

	def test_reviewer_and_auditor_cannot_read_the_representative_identification(self):
		secret_field = "contanext_gt_legal_representative_id"
		company = frappe.get_doc("Company", self.company_name)
		company.set(secret_field, "ID-REP-205")
		with patch("frappe.get_roles", return_value=["System Manager"]):
			company.save(ignore_permissions=True)

		for role in ("Accounts Manager", "GT Books Reviewer", "GT Books Auditor"):
			with self.subTest(role=role):
				company = frappe.get_doc("Company", self.company_name)
				self.assertTrue(company.get(secret_field))
				previous_user = frappe.session.user
				try:
					frappe.session.user = f"fisc-205-{role}@example.com"
					with patch("frappe.get_roles", return_value=[role]):
						company.apply_fieldlevel_read_permissions()
				finally:
					frappe.session.user = previous_user

				self.assertFalse(company.get(secret_field))

	def test_only_approved_roles_retain_the_masked_representative_identification(self):
		secret_field = "contanext_gt_legal_representative_id"
		company = frappe.get_doc("Company", self.company_name)
		company.set(secret_field, "ID-REP-205")
		with patch("frappe.get_roles", return_value=["System Manager"]):
			company.save(ignore_permissions=True)

		for role in ("System Manager", "GT Books Manager"):
			with self.subTest(role=role):
				company = frappe.get_doc("Company", self.company_name)
				previous_user = frappe.session.user
				try:
					frappe.session.user = f"fisc-205-{role}@example.com"
					with patch("frappe.get_roles", return_value=[role]):
						company.apply_fieldlevel_read_permissions()
				finally:
					frappe.session.user = previous_user

				self.assertTrue(company.get(secret_field))

	def test_new_company_is_not_forced_to_have_complete_fiscal_configuration(self):
		company = frappe.new_doc("Company")
		company.company_name = "Empresa inicial incompleta"

		with patch("frappe.get_roles", return_value=["Accounts Manager"]):
			validate_company_fiscal_changes(company)
