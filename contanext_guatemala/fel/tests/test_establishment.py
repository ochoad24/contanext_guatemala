import frappe
from frappe.tests.utils import FrappeTestCase


class TestGTFELestablishment(FrappeTestCase):
	def _company(self, marker):
		suffix = frappe.generate_hash(length=5).upper()
		name = f"FEL Establishment {marker} {suffix}"
		return frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": name,
				"abbr": f"{marker}{suffix[:4]}",
				"country": "Guatemala",
				"default_currency": "GTQ",
			}
		).insert(ignore_permissions=True)

	def _address(self, company):
		return frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": company.name,
				"address_type": "Billing",
				"address_line1": "Zona 1",
				"city": "Guatemala",
				"country": "Guatemala",
				"links": [{"link_doctype": "Company", "link_name": company.name}],
			}
		).insert(ignore_permissions=True)

	def _establishment(self, company, address, code="1", **overrides):
		values = {
			"doctype": "GT FEL Establishment",
			"company": company.name,
			"establishment_code": code,
			"trade_name": company.name,
			"address": address.name,
			"is_active": 1,
		}
		values.update(overrides)
		return frappe.get_doc(values)

	def test_accepts_address_linked_to_same_company(self):
		company = self._company("A")
		address = self._address(company)
		establishment = self._establishment(company, address, is_default=1).insert(ignore_permissions=True)

		self.assertEqual(establishment.company, company.name)
		self.assertEqual(establishment.address, address.name)

	def test_rejects_address_from_another_company(self):
		company_a = self._company("A")
		company_b = self._company("B")
		address_b = self._address(company_b)

		with self.assertRaisesRegex(frappe.ValidationError, "misma empresa"):
			self._establishment(company_a, address_b).insert(ignore_permissions=True)

	def test_rejects_duplicate_code_and_second_default(self):
		company = self._company("U")
		address = self._address(company)
		self._establishment(company, address, code="1", is_default=1).insert(ignore_permissions=True)

		with self.assertRaisesRegex(frappe.ValidationError, "código de establecimiento"):
			self._establishment(company, address, code="1").insert(ignore_permissions=True)
		with self.assertRaisesRegex(frappe.ValidationError, "predeterminado"):
			self._establishment(company, address, code="2", is_default=1).insert(ignore_permissions=True)

	def test_rejects_invalid_validity_and_inactive_default(self):
		company = self._company("D")
		address = self._address(company)

		with self.assertRaisesRegex(frappe.ValidationError, "fecha final"):
			self._establishment(company, address, valid_from="2026-10-30", valid_until="2026-01-01").insert(
				ignore_permissions=True
			)
		with self.assertRaisesRegex(frappe.ValidationError, "debe estar activo"):
			self._establishment(company, address, is_active=0, is_default=1).insert(ignore_permissions=True)
