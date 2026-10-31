from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils.password import set_encrypted_password

from contanext_guatemala.fiscal.setup import (
	COMPANY_FISCAL_FIELDNAMES,
	COMPANY_FISCAL_NON_SECRET_FIELDNAMES,
	COMPANY_FISCAL_PERMISSION_MATRIX,
	COMPANY_FISCAL_SECRET_FIELDNAMES,
	get_company_fiscal_custom_fields,
	install_company_fiscal_custom_fields,
)


COMPANY_FISCAL_LAYOUT = (
	("contanext_gt_fiscal_tab", "Tab Break", "Configuración fiscal de ContaNext"),
	("contanext_gt_identity_section", "Section Break", "Identidad fiscal"),
	("contanext_gt_books_section", "Section Break", "Información contable"),
	("contanext_gt_signers_section", "Section Break", "Responsables"),
	("contanext_gt_fel_section", "Section Break", "Factura Electrónica en Línea — FEL"),
)

COMPANY_ACCOUNTING_AND_SIGNER_FIELDS = {
	"contanext_gt_accounting_framework": {
		"fieldtype": "Select",
		"label": "Marco contable",
		"options": "\nNIIF\nNIIF para PYMES\nBase especial aprobada",
	},
	"contanext_gt_legal_representative_name": {
		"fieldtype": "Data",
		"label": "Representante legal",
	},
	"contanext_gt_legal_representative_id": {
		"fieldtype": "Password",
		"label": "Identificación del representante",
	},
	"contanext_gt_accountant_name": {
		"fieldtype": "Data",
		"label": "Contador",
	},
	"contanext_gt_accountant_nit": {
		"fieldtype": "Data",
		"label": "NIT del contador",
	},
	"contanext_gt_accountant_registration": {
		"fieldtype": "Data",
		"label": "Registro profesional del contador",
	},
	"contanext_gt_accountant_email": {
		"fieldtype": "Data",
		"label": "Correo del contador",
		"options": "Email",
	},
}

COMPANY_FEL_FIELDS = {
	"contanext_gt_fel_enabled": {
		"fieldtype": "Check",
		"label": "FEL habilitado",
		"default": "0",
	},
	"contanext_gt_fel_provider": {
		"fieldtype": "Select",
		"label": "Adaptador de certificador",
		"depends_on": "eval:doc.contanext_gt_fel_enabled",
		"options": "\nTEKRA",
	},
	"contanext_gt_fel_policy": {
		"fieldtype": "Select",
		"label": "Política FEL",
		"default": "NEVER",
		"options": "NEVER\nALWAYS\nSELECTED_CUSTOMERS\nASK_EACH_TIME",
	},
	"contanext_gt_tekra_environment": {
		"fieldtype": "Select",
		"label": "Ambiente TEKRA",
		"default": "SANDBOX",
		"options": "SANDBOX\nPRODUCTION",
	},
	"contanext_gt_fel_notice": {
		"fieldtype": "HTML",
		"label": "Advertencia FEL",
	},
}


class TestCompanyFiscalCustomFields(IntegrationTestCase):
	def test_legacy_fiscal_doctypes_are_not_installed(self):
		for doctype in ("ContaNext Tax Profile", "ContaNext Fiscal Settings"):
			self.assertFalse(frappe.db.exists("DocType", doctype))

	def test_definition_matches_the_approved_contract(self):
		fields = get_company_fiscal_custom_fields()["Company"]
		self.assertEqual(tuple(field["fieldname"] for field in fields), COMPANY_FISCAL_FIELDNAMES)
		self.assertEqual(len(fields), len(COMPANY_FISCAL_FIELDNAMES))

		by_name = {field["fieldname"]: field for field in fields}
		self.assertEqual(by_name["contanext_gt_fiscal_tab"]["insert_after"], "dashboard_tab")
		self.assertEqual(
			by_name["contanext_gt_fiscal_tab"]["depends_on"], 'eval:doc.country==="Guatemala"'
		)
		self.assertEqual(by_name["contanext_gt_fiscal_address"]["options"], "Address")
		self.assertEqual(by_name["contanext_gt_accountant_email"]["options"], "Email")
		self.assertEqual(by_name["contanext_gt_legal_representative_id"]["fieldtype"], "Password")
		self.assertEqual(by_name["contanext_gt_fel_enabled"]["default"], "0")
		self.assertNotIn("contanext_gt_legal_name", by_name)
		self.assertNotIn("contanext_gt_nit", by_name)
		for fieldname in COMPANY_FISCAL_NON_SECRET_FIELDNAMES:
			self.assertEqual(by_name[fieldname]["permlevel"], 1)
		self.assertEqual(COMPANY_FISCAL_SECRET_FIELDNAMES, ("contanext_gt_legal_representative_id",))
		for fieldname in COMPANY_FISCAL_SECRET_FIELDNAMES:
			self.assertEqual(by_name[fieldname]["permlevel"], 2)

		for previous, field in zip(
			("dashboard_tab", *COMPANY_FISCAL_FIELDNAMES[:-1]), fields, strict=True
		):
			self.assertEqual(field["insert_after"], previous)

	def test_definition_has_the_spanish_tab_and_sections_in_contract_order(self):
		fields = get_company_fiscal_custom_fields()["Company"]
		by_name = {field["fieldname"]: field for field in fields}

		self.assertEqual(
			tuple(field["fieldname"] for field in fields if field["fieldtype"] in {"Tab Break", "Section Break"}),
			tuple(fieldname for fieldname, _fieldtype, _label in COMPANY_FISCAL_LAYOUT),
		)
		for fieldname, fieldtype, label in COMPANY_FISCAL_LAYOUT:
			with self.subTest(fieldname=fieldname):
				self.assertEqual(by_name[fieldname]["fieldtype"], fieldtype)
				self.assertEqual(by_name[fieldname]["label"], label)

		self.assertEqual(
			by_name["contanext_gt_fiscal_tab"]["depends_on"],
			'eval:doc.country==="Guatemala"',
		)

	def test_accounting_and_signer_definitions_match_the_approved_contract(self):
		by_name = {
			field["fieldname"]: field for field in get_company_fiscal_custom_fields()["Company"]
		}

		for fieldname, expected in COMPANY_ACCOUNTING_AND_SIGNER_FIELDS.items():
			with self.subTest(fieldname=fieldname):
				field = by_name[fieldname]
				self.assertEqual(field["fieldtype"], expected["fieldtype"])
				self.assertEqual(field["label"], expected["label"])
				if "options" in expected:
					self.assertEqual(field.get("options"), expected["options"])
				self.assertNotIn("default", field)

	def test_fel_definitions_match_the_approved_phase_one_contract(self):
		by_name = {
			field["fieldname"]: field for field in get_company_fiscal_custom_fields()["Company"]
		}

		for fieldname, expected in COMPANY_FEL_FIELDS.items():
			with self.subTest(fieldname=fieldname):
				field = by_name[fieldname]
				self.assertEqual(field["fieldtype"], expected["fieldtype"])
				self.assertEqual(field["label"], expected["label"])
				self.assertEqual(field.get("default"), expected.get("default"))
				self.assertEqual(field.get("depends_on"), expected.get("depends_on"))
				if "options" in expected:
					self.assertEqual(field.get("options"), expected["options"])

		notice = by_name["contanext_gt_fel_notice"]["options"]
		self.assertIn("preflight completo", notice)
		self.assertIn("variables de entorno", notice)
		self.assertIn("homologación", notice)

	def test_installation_is_idempotent(self):
		install_company_fiscal_custom_fields()
		install_company_fiscal_custom_fields()

		rows = frappe.get_all(
			"Custom Field",
			filters={"dt": "Company", "fieldname": ["in", COMPANY_FISCAL_FIELDNAMES]},
			fields=["fieldname", "fieldtype", "insert_after", "options", "depends_on", "default", "permlevel"],
		)
		self.assertEqual(len(rows), len(COMPANY_FISCAL_FIELDNAMES))
		self.assertEqual({row.fieldname for row in rows}, set(COMPANY_FISCAL_FIELDNAMES))

		installed = {row.fieldname: row for row in rows}
		self.assertEqual(installed["contanext_gt_fiscal_address"].fieldtype, "Link")
		self.assertEqual(installed["contanext_gt_fiscal_address"].options, "Address")
		self.assertEqual(installed["contanext_gt_fiscal_tab"].insert_after, "dashboard_tab")
		self.assertEqual(
			installed["contanext_gt_fel_provider"].depends_on,
			"eval:doc.contanext_gt_fel_enabled",
		)

		meta = frappe.get_meta("Company", cached=False)
		for fieldname in COMPANY_FISCAL_FIELDNAMES:
			self.assertIsNotNone(meta.get_field(fieldname))

		installed_fieldnames = tuple(field.fieldname for field in meta.fields)
		self.assertEqual(
			tuple(sorted(COMPANY_FISCAL_FIELDNAMES, key=installed_fieldnames.index)),
			COMPANY_FISCAL_FIELDNAMES,
		)
		for fieldname, fieldtype, label in COMPANY_FISCAL_LAYOUT:
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertEqual(field.fieldtype, fieldtype)
				self.assertEqual(field.label, label)

		self.assertEqual(
			meta.get_field("contanext_gt_fiscal_tab").depends_on,
			'eval:doc.country==="Guatemala"',
		)
		for fieldname in COMPANY_FISCAL_NON_SECRET_FIELDNAMES:
			self.assertEqual(meta.get_field(fieldname).permlevel, 1)
		for fieldname in COMPANY_FISCAL_SECRET_FIELDNAMES:
			self.assertEqual(meta.get_field(fieldname).permlevel, 2)

	def test_fiscal_permission_matrix_is_installed_idempotently(self):
		install_company_fiscal_custom_fields()
		install_company_fiscal_custom_fields()

		meta = frappe.get_meta("Company", cached=False)
		for permlevel, role_matrix in COMPANY_FISCAL_PERMISSION_MATRIX.items():
			for role, expected_rights in role_matrix.items():
				with self.subTest(permlevel=permlevel, role=role):
					rows = [
						permission
						for permission in meta.permissions
						if permission.role == role and permission.permlevel == permlevel
					]
					self.assertEqual(len(rows), 1)
					permission = rows[0]
					self.assertEqual(permission.read, int("read" in expected_rights))
					self.assertEqual(permission.write, int("write" in expected_rights))
					self.assertEqual(permission.create, int("create" in expected_rights))

		level_one_roles = {
			permission.role for permission in meta.permissions if permission.permlevel == 1
		}
		self.assertEqual(level_one_roles, set(COMPANY_FISCAL_PERMISSION_MATRIX[1]))
		level_two_roles = {
			permission.role for permission in meta.permissions if permission.permlevel == 2
		}
		self.assertEqual(level_two_roles, set(COMPANY_FISCAL_PERMISSION_MATRIX[2]))
		for role in COMPANY_FISCAL_PERMISSION_MATRIX[0]:
			self.assertTrue(
				any(permission.role == role and permission.permlevel == 0 for permission in meta.permissions)
			)

	def test_fiscal_permission_matrix_grants_the_expected_permlevel_access(self):
		install_company_fiscal_custom_fields()
		meta = frappe.get_meta("Company", cached=False)
		expected = {
			"System Manager": {"read": True, "write": True},
			"GT Books Manager": {"read": True, "write": True},
			"Accounts Manager": {"read": True, "write": False},
			"GT Books Reviewer": {"read": True, "write": False},
			"GT Books Auditor": {"read": True, "write": False},
			"GT Books User": {"read": False, "write": False},
		}

		for role, rights in expected.items():
			with self.subTest(role=role), patch("frappe.get_roles", return_value=[role]):
				self.assertEqual(1 in meta.get_permlevel_access("read"), rights["read"])
				self.assertEqual(1 in meta.get_permlevel_access("write"), rights["write"])
				self.assertEqual(
					2 in meta.get_permlevel_access("read"),
					role in {"System Manager", "GT Books Manager"},
				)
				self.assertEqual(
					2 in meta.get_permlevel_access("write"),
					role in {"System Manager", "GT Books Manager"},
				)

		base_expected = {
			"GT Books Manager": {"read": True, "write": True},
			"GT Books Reviewer": {"read": True, "write": False},
			"GT Books Auditor": {"read": True, "write": False},
		}
		for role, rights in base_expected.items():
			with self.subTest(base_role=role), patch("frappe.get_roles", return_value=[role]):
				self.assertEqual(0 in meta.get_permlevel_access("read"), rights["read"])
				self.assertEqual(0 in meta.get_permlevel_access("write"), rights["write"])

	def test_accounting_and_signer_fields_are_installed_and_persist_on_company(self):
		install_company_fiscal_custom_fields()
		meta = frappe.get_meta("Company", cached=False)

		for fieldname, expected in COMPANY_ACCOUNTING_AND_SIGNER_FIELDS.items():
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field)
				self.assertEqual(field.fieldtype, expected["fieldtype"])
				self.assertEqual(field.label, expected["label"])
				self.assertEqual(field.options, expected.get("options"))
				self.assertFalse(field.default)

		companies = frappe.get_all("Company", pluck="name", limit=1)
		if companies:
			company_name = companies[0]
		else:
			suffix = frappe.generate_hash(length=6).upper()
			company_name = f"Fiscal Setup {suffix}"
			frappe.get_doc(
				{
					"doctype": "Company",
					"name": company_name,
					"company_name": company_name,
					"abbr": f"FS{suffix[:4]}",
					"country": "Guatemala",
					"default_currency": "GTQ",
					"valuation_method": "FIFO",
				}
			).db_insert()
		frappe.db.set_value("Company", company_name, "country", "Guatemala")
		company = frappe.get_doc("Company", company_name)
		values = {
			"contanext_gt_accounting_framework": "NIIF para PYMES",
			"contanext_gt_legal_representative_name": "María Representante",
			"contanext_gt_legal_representative_id": "ID-REP-104",
			"contanext_gt_accountant_name": "Carlos Contador",
			"contanext_gt_accountant_nit": "1234567-8",
			"contanext_gt_accountant_registration": "CPA-104",
			"contanext_gt_accountant_email": "contador104@example.com",
		}
		frappe.db.set_value(
			"Company",
			company_name,
			{fieldname: value for fieldname, value in values.items() if fieldname != "contanext_gt_legal_representative_id"},
			update_modified=False,
		)
		set_encrypted_password(
			"Company",
			company_name,
			values["contanext_gt_legal_representative_id"],
			fieldname="contanext_gt_legal_representative_id",
		)
		company.reload()

		for fieldname, value in values.items():
			with self.subTest(fieldname=fieldname):
				if fieldname == "contanext_gt_legal_representative_id":
					self.assertEqual(company.get_password(fieldname), value)
				else:
					self.assertEqual(company.get(fieldname), value)

	def test_fel_fields_are_installed_with_visible_warning_and_disabled_default(self):
		install_company_fiscal_custom_fields()
		meta = frappe.get_meta("Company", cached=False)

		for fieldname, expected in COMPANY_FEL_FIELDS.items():
			with self.subTest(fieldname=fieldname):
				field = meta.get_field(fieldname)
				self.assertIsNotNone(field)
				self.assertEqual(field.fieldtype, expected["fieldtype"])
				self.assertEqual(field.label, expected["label"])
				self.assertEqual(field.depends_on, expected.get("depends_on"))

		notice = meta.get_field("contanext_gt_fel_notice").options
		self.assertIn("preflight completo", notice)
		self.assertIn("variables de entorno", notice)
		self.assertIn("homologación", notice)
		self.assertEqual(meta.get_field("contanext_gt_fel_enabled").default, "0")
		self.assertEqual(frappe.new_doc("Company").contanext_gt_fel_enabled, 0)
