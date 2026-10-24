import json
import unittest
from pathlib import Path

from contanext_guatemala.books.catalog import diagnose_accounts, diagnose_template


class TestCatalog(unittest.TestCase):
	def test_pinned_guatemala_template_has_valid_roots(self):
		apps_directory = Path(__file__).resolve().parents[4]
		template = (
			apps_directory
			/ "erpnext/erpnext/accounts/doctype/account/chart_of_accounts/verified/gt_cuentas_plantilla.json"
		)
		data = json.loads(template.read_text(encoding="utf-8"))
		root_findings = [
			finding
			for finding in diagnose_template(data["tree"])
			if finding.code == "INVALID_ROOT_TYPE"
		]
		self.assertEqual(root_findings, [])

	def test_existing_catalog_diagnostic_is_read_only_and_blocking(self):
		findings = diagnose_accounts(
			[
				{
					"name": "Patrimonio - GT",
					"account_name": "Patrimonio",
					"root_type": "Asset",
					"parent_account": "",
					"account_number": "3",
					"is_group": 1,
				},
				{"name": "Caja", "account_number": "1.1", "is_group": 0},
				{"name": "Banco EJEMPLO", "account_number": "1.1", "is_group": 0},
				{"name": "Ventas", "account_number": "", "is_group": 0},
			]
		)
		self.assertEqual(
			{finding.code for finding in findings},
			{
				"INVALID_ROOT_TYPE",
				"EXAMPLE_ACCOUNT",
				"DUPLICATE_ACCOUNT_NUMBER",
				"MISSING_ACCOUNT_NUMBER",
				"MISSING_ROOT",
			},
		)


if __name__ == "__main__":
	unittest.main()
