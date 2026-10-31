from unittest import TestCase

from contanext_guatemala.fiscal.setup import get_company_fiscal_custom_fields


class TestCompanyFELSettingsFields(TestCase):
	def test_non_secret_company_configuration_is_explicit(self):
		fields = {
			field["fieldname"]: field
			for field in get_company_fiscal_custom_fields()["Company"]
		}

		self.assertEqual(fields["contanext_gt_fel_provider"]["fieldtype"], "Select")
		self.assertEqual(fields["contanext_gt_fel_provider"]["options"], "\nTEKRA")
		self.assertIn("ASK_EACH_TIME", fields["contanext_gt_fel_policy"]["options"])
		self.assertEqual(fields["contanext_gt_fel_phrases"]["options"], "GT FEL Phrase")
		self.assertEqual(fields["contanext_gt_tekra_environment"]["default"], "SANDBOX")
		self.assertEqual(fields["contanext_gt_tekra_sign_issuer"]["default"], "1")
		self.assertEqual(fields["contanext_gt_fel_policy"]["permlevel"], 3)

	def test_no_company_field_persists_tekra_secrets(self):
		fieldnames = {
			field["fieldname"]
			for field in get_company_fiscal_custom_fields()["Company"]
		}
		for forbidden in ("password", "secret", "contract", "client"):
			self.assertFalse(any(forbidden in fieldname for fieldname in fieldnames))
