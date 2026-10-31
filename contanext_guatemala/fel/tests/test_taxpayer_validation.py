import frappe
from frappe.tests.utils import FrappeTestCase

from contanext_guatemala.fel.taxpayer import (
	invalidate_customer_validation_on_identity_change,
	normalize_taxpayer_identifier,
	taxpayer_lookup_key,
)


class TestTaxpayerValidation(FrappeTestCase):
	def _validation(self, identifier="1234567-8", **overrides):
		values = {
			"doctype": "GT Taxpayer Validation",
			"provider": "TEKRA",
			"environment": "SANDBOX",
			"identification_type": "NIT",
			"identifier": identifier,
			"status": "VALID",
			"is_current": 1,
		}
		values.update(overrides)
		return frappe.get_doc(values)

	def test_normalization_and_lookup_key_separate_type_and_environment(self):
		self.assertEqual(normalize_taxpayer_identifier("NIT", " 1234567-k "), "1234567K")
		self.assertEqual(normalize_taxpayer_identifier("CUI", "1234 56789 0101"), "1234567890101")
		self.assertNotEqual(
			taxpayer_lookup_key("TEKRA", "SANDBOX", "NIT", "1234567K"),
			taxpayer_lookup_key("TEKRA", "PRODUCTION", "NIT", "1234567K"),
		)

	def test_only_one_current_result_exists_per_logical_key(self):
		first = self._validation().insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "validación tributaria vigente"):
			self._validation().insert(ignore_permissions=True)

		first.is_current = 0
		first.save(ignore_permissions=True)
		second = self._validation(previous_validation=first.name).insert(ignore_permissions=True)
		self.assertEqual(second.previous_validation, first.name)

	def test_customer_identity_change_clears_derived_link(self):
		previous = frappe._dict(
			tax_id="1234567-8",
			contanext_gt_identification_type="NIT",
		)
		customer = frappe._dict(
			tax_id="9999999-9",
			contanext_gt_identification_type="NIT",
			contanext_gt_taxpayer_validation="VALIDATION-1",
			contanext_gt_taxpayer_validation_status="VALID",
			contanext_gt_taxpayer_returned_name="Nombre SAT",
			is_new=lambda: False,
			get_doc_before_save=lambda: previous,
		)

		invalidate_customer_validation_on_identity_change(customer)

		self.assertIsNone(customer.contanext_gt_taxpayer_validation)
		self.assertIsNone(customer.contanext_gt_taxpayer_validation_status)
		self.assertIsNone(customer.contanext_gt_taxpayer_returned_name)
