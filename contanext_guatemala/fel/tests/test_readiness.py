from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from contanext_guatemala.fel.readiness import diagnose_fel_readiness
from contanext_guatemala.fel.settings import FELConfigurationError


class TestFELReadiness(TestCase):
	def test_reports_gaps_without_writing_or_inventing_values(self):
		company = SimpleNamespace(
			company_name="Company A",
			tax_id="1234567-8",
			contanext_gt_fiscal_address="Address A",
			contanext_gt_fel_provider="TEKRA",
			contanext_gt_fel_policy="ALWAYS",
			contanext_gt_vat_affiliation="GEN",
			contanext_gt_price_tax_mode="TAX_INCLUDED",
			contanext_gt_tekra_environment="SANDBOX",
			contanext_gt_default_establishment=None,
		)
		with (
			patch("contanext_guatemala.fel.readiness.frappe.db.get_value", return_value=company),
			patch("contanext_guatemala.fel.readiness.frappe.db.count", side_effect=[0, 3]),
			patch(
				"contanext_guatemala.fel.readiness.frappe.get_all",
				return_value=[SimpleNamespace(name="CUST-1", tax_id=None, contanext_gt_identification_type=None)],
			),
			patch(
				"contanext_guatemala.fel.readiness.validate_tekra_environment",
				side_effect=FELConfigurationError("missing"),
			),
			patch("contanext_guatemala.fel.readiness.frappe.db.set_value", Mock()) as set_value,
		):
			assessment = diagnose_fel_readiness("Company A")

		self.assertFalse(assessment["ready"])
		self.assertEqual(
			{check["code"]: check["count"] for check in assessment["checks"] if check["status"] == "FAIL"},
			{"DEFAULT_ESTABLISHMENT": 0, "ACTIVE_ESTABLISHMENTS": 0, "ITEM_KIND": 3, "CUSTOMER_IDENTIFICATION": 1, "ENVIRONMENT": 0},
		)
		set_value.assert_not_called()

	def test_returns_structured_read_only_assessment(self):
		company = SimpleNamespace(
			company_name="Company A",
			tax_id="1234567-8",
			contanext_gt_fiscal_address="Address A",
			contanext_gt_fel_provider="TEKRA",
			contanext_gt_fel_policy="ALWAYS",
			contanext_gt_vat_affiliation="GEN",
			contanext_gt_price_tax_mode="TAX_INCLUDED",
			contanext_gt_tekra_environment="SANDBOX",
			contanext_gt_default_establishment="GT-FEL-EST-1",
		)
		with (
			patch("contanext_guatemala.fel.readiness.frappe.db.get_value", return_value=company),
			patch("contanext_guatemala.fel.readiness.frappe.db.count", side_effect=[1, 0]),
			patch("contanext_guatemala.fel.readiness.frappe.get_all", return_value=[]),
			patch("contanext_guatemala.fel.readiness.validate_tekra_environment"),
			patch("contanext_guatemala.fel.readiness.frappe.db.set_value", Mock()) as set_value,
		):
			assessment = diagnose_fel_readiness("Company A")

		self.assertTrue(assessment["ready"])
		self.assertEqual({check["status"] for check in assessment["checks"]}, {"PASS"})
		set_value.assert_not_called()
