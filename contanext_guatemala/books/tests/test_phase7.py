import unittest
from types import SimpleNamespace
from unittest.mock import patch

from contanext_guatemala.books.file_security import restrict_controlled_book_file
from contanext_guatemala.books.migration import build_migration_assessment
from contanext_guatemala.books.upgrade_contract import assert_supported_runtime, build_upgrade_contract


class TestTechnicalClosureContracts(unittest.TestCase):
	def test_controlled_files_delegate_to_parent_and_packages_deny_direct_read(self):
		package_file = SimpleNamespace(
			attached_to_doctype="GT Requirement Package", attached_to_name="GT-REQ-1"
		)
		self.assertFalse(restrict_controlled_book_file(package_file, "auditor@example.com", "read"))

		run_file = SimpleNamespace(
			attached_to_doctype="GT Accounting Book Run", attached_to_name="GT-RUN-1"
		)
		fake_frappe = SimpleNamespace(has_permission=lambda *args, **kwargs: False)
		with patch.dict("sys.modules", {"frappe": fake_frappe}):
			self.assertFalse(restrict_controlled_book_file(run_file, "other-company@example.com", "read"))

		unrelated = SimpleNamespace(attached_to_doctype="Sales Invoice", attached_to_name="SINV-1")
		self.assertTrue(restrict_controlled_book_file(unrelated, "user@example.com", ptype="read"))
		self.assertTrue(restrict_controlled_book_file(unrelated, "user@example.com", ptype="create"))
		self.assertTrue(restrict_controlled_book_file(package_file, "user@example.com", ptype="create"))

	def test_existing_company_assessment_is_deterministic_and_read_only(self):
		arguments = {
			"country": "Guatemala",
			"currency": "GTQ",
			"account_findings": [],
			"fiscal_missing_fields": [],
			"settings_count": 1,
			"draft_transaction_count": 0,
			"gl_entry_count": 25,
			"stock_ledger_entry_count": 10,
			"book_run_count": 0,
		}
		first = build_migration_assessment("ACME", **arguments)
		second = build_migration_assessment("ACME", **arguments)
		self.assertEqual(first, second)
		self.assertEqual(first["blocking_failures"], 0)
		self.assertEqual(first["manual_reviews"], 1)
		self.assertTrue(first["dry_run"])
		self.assertEqual(first["mutations_performed"], [])
		self.assertFalse(first["automatic_ledger_migration_allowed"])
		self.assertEqual(first["version"], 2)
		self.assertNotIn("tax_profile_count", first["facts"])

	def test_migration_assessment_fails_closed_on_structural_findings(self):
		assessment = build_migration_assessment(
			"ACME",
			country="Guatemala",
			currency="USD",
			account_findings=[{"code": "INVALID_ROOT_TYPE", "severity": "BLOCKER"}],
			fiscal_missing_fields=["NIT", "Dirección fiscal"],
			settings_count=0,
			draft_transaction_count=2,
			gl_entry_count=0,
			stock_ledger_entry_count=0,
			book_run_count=0,
		)
		self.assertEqual(assessment["blocking_failures"], 5)

	def test_upgrade_contract_is_stable_and_rejects_other_majors(self):
		contract = build_upgrade_contract()
		self.assertEqual(contract, build_upgrade_contract())
		self.assertEqual(
			contract["contract_sha256"],
			"8510454d482f12c3a7c01a56cd4c6093c6f0a9ffec9c73704c794c40de9d0585",
		)
		assert_supported_runtime(frappe_version="16.53.0", erpnext_version="v16.52.1")
		with self.assertRaises(RuntimeError):
			assert_supported_runtime(frappe_version="17.0.0", erpnext_version="16.52.1")


if __name__ == "__main__":
	unittest.main()
