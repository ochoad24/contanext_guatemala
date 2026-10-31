from unittest.mock import patch

import frappe

from erpnext.tests.utils import ERPNextTestSuite

from contanext_guatemala.fiscal.company import get_company_fiscal_address_options


class TestCompanyFiscalAddressQuery(ERPNextTestSuite):
	def setUp(self):
		super().setUp()
		self.load_test_records("Company")
		companies = frappe.get_all("Company", pluck="name", limit=2, order_by="name")
		self.company = companies[0]
		self.other_company = companies[-1]

		self.eligible_address = self._make_address(
			"CN Fiscal Eligible",
			company=self.company,
			is_your_company_address=1,
			disabled=0,
		)
		self.disabled_address = self._make_address(
			"CN Fiscal Disabled",
			company=self.company,
			is_your_company_address=1,
			disabled=1,
		)
		self.non_company_address = self._make_address(
			"CN Fiscal Not Company",
			company=self.company,
			is_your_company_address=0,
			disabled=0,
		)
		if self.other_company != self.company:
			self.other_company_address = self._make_address(
				"CN Fiscal Other Company",
				company=self.other_company,
				is_your_company_address=1,
				disabled=0,
			)
		else:
			self.other_company_address = None

	def _make_address(
		self,
		title: str,
		*,
		company: str,
		is_your_company_address: int,
		disabled: int,
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

	def _query(self, txt: str = "CN Fiscal") -> list[tuple[str, ...]]:
		return get_company_fiscal_address_options(
			"Address",
			txt,
			"name",
			0,
			20,
			{"company": self.company},
		)

	def test_query_only_returns_active_company_addresses(self):
		results = self._query()
		names = {row[0] for row in results}

		self.assertIn(self.eligible_address, names)
		self.assertNotIn(self.disabled_address, names)
		self.assertNotIn(self.non_company_address, names)
		if self.other_company_address:
			self.assertNotIn(self.other_company_address, names)

	def test_query_requires_a_persisted_company(self):
		with patch("frappe.has_permission") as has_permission:
			results = get_company_fiscal_address_options(
				"Address", "", "name", 0, 20, {"company": ""}
			)

		self.assertEqual(results, [])
		has_permission.assert_not_called()

	def test_query_checks_select_permission_for_the_company(self):
		with patch("frappe.has_permission") as has_permission:
			self._query()

		has_permission.assert_called_once_with(
			"Company", ptype="select", doc=self.company, throw=True
		)
