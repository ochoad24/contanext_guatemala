import frappe

from erpnext.tests.utils import ERPNextTestSuite


class TestCompanyFiscalAddressValidation(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
		self.load_test_records("Company")
		companies = frappe.get_all("Company", pluck="name", limit=2, order_by="name")
		self.company = companies[0]
		self.other_company = companies[-1]
		for company in {self.company, self.other_company}:
			frappe.db.set_value("Company", company, "country", "Guatemala")

	def _make_address(
		self,
		title: str,
		*,
		company: str,
		is_your_company_address: int = 1,
		disabled: int = 0,
	) -> str:
		address = frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": title,
				"address_type": "Office",
				"address_line1": f"{title} Line 1",
				"city": "Guatemala",
				"country": "Guatemala",
				"is_your_company_address": is_your_company_address,
				"disabled": disabled,
				"links": [{"link_doctype": "Company", "link_name": company}],
			}
		).insert(ignore_permissions=True)
		if not is_your_company_address:
			frappe.db.set_value("Address", address.name, "is_your_company_address", 0)
		return address.name

	def _save_fiscal_address(self, address_name: str) -> None:
		company = frappe.get_doc("Company", self.company)
		company.contanext_gt_fiscal_address = address_name
		company.save(ignore_permissions=True)

	def test_company_accepts_an_active_address_linked_to_itself(self):
		address_name = self._make_address("CN Fiscal Validation Eligible", company=self.company)

		self._save_fiscal_address(address_name)

		self.assertEqual(
			frappe.db.get_value("Company", self.company, "contanext_gt_fiscal_address"),
			address_name,
		)

	def test_company_rejects_an_address_linked_to_another_company(self):
		if self.other_company == self.company:
			self.skipTest("The test site needs two companies")
		address_name = self._make_address(
			"CN Fiscal Validation Other Company", company=self.other_company
		)

		with self.assertRaisesRegex(frappe.ValidationError, "no está vinculada a la empresa"):
			self._save_fiscal_address(address_name)

	def test_company_rejects_a_missing_address(self):
		with self.assertRaisesRegex(frappe.LinkValidationError, "Could not find Dirección fiscal"):
			self._save_fiscal_address("CN Fiscal Validation Missing")

	def test_company_rejects_a_disabled_address(self):
		address_name = self._make_address(
			"CN Fiscal Validation Disabled", company=self.company, disabled=1
		)

		with self.assertRaisesRegex(frappe.ValidationError, "está deshabilitada"):
			self._save_fiscal_address(address_name)

	def test_company_rejects_a_non_company_address(self):
		address_name = self._make_address(
			"CN Fiscal Validation Not Company",
			company=self.company,
			is_your_company_address=0,
		)

		with self.assertRaisesRegex(frappe.ValidationError, "no es una dirección de la empresa"):
			self._save_fiscal_address(address_name)

	def test_company_can_be_saved_without_a_fiscal_address(self):
		company = frappe.get_doc("Company", self.company)
		company.contanext_gt_fiscal_address = None

		company.save(ignore_permissions=True)

		self.assertFalse(company.contanext_gt_fiscal_address)
