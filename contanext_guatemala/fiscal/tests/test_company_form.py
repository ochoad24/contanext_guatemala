from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase


COMPANY_FORM_SCRIPT = Path(__file__).resolve().parents[2] / "public" / "js" / "company_fiscal.js"


class TestCompanyFiscalForm(IntegrationTestCase):
	def test_company_uses_native_legal_name_and_nit_fields(self):
		meta = frappe.get_meta("Company", cached=False)

		self.assertEqual(meta.get_field("company_name").fieldtype, "Data")
		self.assertEqual(meta.get_field("tax_id").fieldtype, "Data")
		self.assertEqual(meta.get_field("contanext_gt_identity_summary").fieldtype, "HTML")
		self.assertIsNone(meta.get_field("contanext_gt_legal_name"))
		self.assertIsNone(meta.get_field("contanext_gt_nit"))

	def test_company_form_renders_and_refreshes_the_native_identity(self):
		hooks = frappe.get_hooks("doctype_js")
		company_scripts = hooks.get("Company", [])
		if isinstance(company_scripts, str):
			company_scripts = [company_scripts]

		self.assertIn("public/js/company_fiscal.js", company_scripts)
		script = COMPANY_FORM_SCRIPT.read_text(encoding="utf-8")
		self.assertIn("frm.doc.company_name", script)
		self.assertIn("frm.doc.tax_id", script)
		self.assertIn("frappe.utils.escape_html", script)
		self.assertIn("company_name(frm)", script)
		self.assertIn("tax_id(frm)", script)
		self.assertIn("grid-template-columns: repeat(auto-fit, minmax(220px, 1fr))", script)
		self.assertIn("overflow-wrap: anywhere", script)
		self.assertNotIn('class="form-grid"', script)
		self.assertNotIn("like-disabled-input", script)
		self.assertNotIn("sortable-handle", script)
		self.assertNotIn("frm.set_value", script)

	def test_company_form_filters_fiscal_address_by_persisted_company(self):
		script = COMPANY_FORM_SCRIPT.read_text(encoding="utf-8")

		self.assertIn('frm.set_query("contanext_gt_fiscal_address"', script)
		self.assertIn(
			"contanext_guatemala.fiscal.company.get_company_fiscal_address_options",
			script,
		)
		self.assertIn('company: frm.is_new() ? "" : frm.doc.name', script)

	def test_company_form_marks_fiscal_fields_read_only_for_non_manager_roles(self):
		script = COMPANY_FORM_SCRIPT.read_text(encoding="utf-8")

		self.assertIn('frappe.user.has_role(role)', script)
		self.assertIn('["System Manager", "GT Books Manager"]', script)
		self.assertIn('new Set(["company_name", "tax_id"])', script)
		self.assertIn('field.df.fieldname.startsWith("contanext_gt_")', script)
		self.assertIn('field.df.permlevel === 1', script)
		self.assertIn('"read_only", can_edit_fiscal_fields ? 0 : 1', script)
