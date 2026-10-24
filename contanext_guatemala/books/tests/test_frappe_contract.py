from unittest.mock import patch

import frappe
from frappe.permissions import add_user_permission
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from erpnext.accounts.report.general_ledger.general_ledger import execute as general_ledger_execute
from erpnext.accounts.report.trial_balance.trial_balance import execute as trial_balance_execute

from contanext_guatemala.books.constants import UNAUTHORIZED_DRAFT_LABEL
from contanext_guatemala.books.file_security import restrict_controlled_book_file
from contanext_guatemala.books.jobs import generate_book_run
from contanext_guatemala.books.migration import assess_existing_company
from contanext_guatemala.books.preflight import execute_preflight
from contanext_guatemala.books.manifests import verify_seal_manifest
from contanext_guatemala.books.requirements import audit_package_download, generate_requirement_package
from contanext_guatemala.books.sealing import seal_book_run
from contanext_guatemala.books.upgrade_contract import assert_supported_runtime, build_upgrade_contract
from contanext_guatemala.contanext_guatemala.doctype.gt_accounting_book_run.gt_accounting_book_run import (
	confirm_print,
	request_generation,
)
from contanext_guatemala.contanext_guatemala.doctype.gt_requirement_package.gt_requirement_package import (
	release,
)


class TestFrappeBooksContract(IntegrationTestCase):
	def test_app_is_installed_with_safe_localization_defaults(self):
		self.assertIn("contanext_guatemala", frappe.get_installed_apps())
		self.assertEqual(frappe.db.get_default("currency"), "GTQ")
		self.assertEqual(frappe.db.get_default("country"), "Guatemala")
		self.assertIn("NO AUTORIZADO", UNAUTHORIZED_DRAFT_LABEL)

	def test_phase_one_roles_and_doctypes_are_installed(self):
		for role in ("GT Books User", "GT Books Reviewer", "GT Books Manager", "GT Books Auditor"):
			self.assertTrue(frappe.db.exists("Role", role))
		for doctype in (
			"GT Accounting Book Settings",
			"GT Accounting Book Run",
			"GT Book Authorization Evidence",
			"GT Book Validation Result",
			"GT Book Artifact",
			"GT Financial Statement Annex",
			"GT Book Run Annex",
			"GT Book Review Event",
			"GT Physical Count Import",
			"GT Physical Count Row",
			"GT Inventory Account Mapping",
			"GT Book Folio Allocation",
			"GT Book Folio Event",
			"GT Book Signed Copy",
			"GT Book Operational Alert",
			"GT Requirement Package",
			"GT Requirement Package Run",
			"GT Requirement Support Index",
			"GT Requirement Package Event",
		):
			self.assertTrue(frappe.db.exists("DocType", doctype))
		self.assertTrue(frappe.db.exists("Report", "GT Existing Company Readiness"))

	def test_runtime_versions_match_the_upgrade_contract(self):
		import erpnext

		assert_supported_runtime(
			frappe_version=frappe.__version__,
			erpnext_version=erpnext.__version__,
		)
		self.assertEqual(
			build_upgrade_contract()["contract_sha256"],
			"8510454d482f12c3a7c01a56cd4c6093c6f0a9ffec9c73704c794c40de9d0585",
		)

	def test_auditor_permissions_are_read_only(self):
		meta = frappe.get_meta("GT Accounting Book Run")
		auditor = next(row for row in meta.permissions if row.role == "GT Books Auditor")
		manager = next(row for row in meta.permissions if row.role == "GT Books Manager")
		self.assertEqual(auditor.read, 1)
		self.assertEqual(auditor.write, 0)
		self.assertEqual(auditor.create, 0)
		self.assertEqual(manager.write, 1)
		self.assertEqual(manager.create, 1)

	def test_controlled_file_hook_rejects_public_attachments(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "File",
					"file_name": "public-book-artifact.txt",
					"content": "contenido de prueba",
					"is_private": 0,
					"attached_to_doctype": "GT Accounting Book Run",
					"attached_to_name": "GT-RUN-NOT-REQUIRED-FOR-PRIVACY-CHECK",
				}
			).insert(ignore_permissions=True)

	def test_legal_mode_is_not_exposed(self):
		meta = frappe.get_meta("GT Accounting Book Run")
		self.assertEqual(meta.get_field("generation_mode").options, "Technical Draft")
		self.assertTrue(meta.get_field("draft_notice").read_only)
		self.assertEqual(meta.get_field("artifacts").options, "GT Book Artifact")
		frameworks = frappe.get_meta("ContaNext Tax Profile").get_field("accounting_framework").options
		self.assertIn("NIIF", frameworks)
		self.assertIn("NIIF para PYMES", frameworks)
		self.assertIn("Base especial aprobada", frameworks)

	def test_company_user_permission_denies_cross_company_read(self):
		suffix = frappe.generate_hash(length=6).upper()
		companies = []
		for marker in ("A", "B"):
			company_name = f"GT Permission {marker} {suffix}"
			frappe.get_doc(
				{
					"doctype": "Company",
					"name": company_name,
					"company_name": company_name,
					"abbr": f"{marker}{suffix[:4]}",
					"country": "Guatemala",
					"default_currency": "GTQ",
				}
			).db_insert()
			companies.append(company_name)

		email = f"gt-books-{suffix.lower()}@example.com"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "GT Books Test",
				"enabled": 1,
				"send_welcome_email": 0,
				"roles": [{"role": "GT Books User"}, {"role": "GT Books Auditor"}],
			}
		).insert(ignore_permissions=True)
		add_user_permission("Company", companies[0], email)

		allowed = frappe.get_doc(
			{"doctype": "GT Accounting Book Run", "company": companies[0], "owner": email}
		)
		denied = frappe.get_doc(
			{"doctype": "GT Accounting Book Run", "company": companies[1], "owner": email}
		)
		self.assertTrue(frappe.has_permission("GT Accounting Book Run", "read", allowed, email))
		self.assertFalse(frappe.has_permission("GT Accounting Book Run", "read", denied, email))
		for doctype in ("GT Requirement Package", "GT Book Operational Alert"):
			allowed_object = frappe.get_doc({"doctype": doctype, "company": companies[0], "owner": email})
			denied_object = frappe.get_doc({"doctype": doctype, "company": companies[1], "owner": email})
			self.assertTrue(frappe.has_permission(doctype, "read", allowed_object, email))
			self.assertFalse(frappe.has_permission(doctype, "read", denied_object, email))

		allowed.db_insert()
		denied.db_insert()
		allowed_file = frappe._dict(
			attached_to_doctype="GT Accounting Book Run", attached_to_name=allowed.name
		)
		denied_file = frappe._dict(
			attached_to_doctype="GT Accounting Book Run", attached_to_name=denied.name
		)
		self.assertTrue(restrict_controlled_book_file(allowed_file, email, "read"))
		self.assertFalse(restrict_controlled_book_file(denied_file, email, "read"))

	def test_preflight_runs_against_frappe_accounting_tables(self):
		suffix = frappe.generate_hash(length=6).upper()
		company_name = f"GT Books Test {suffix}"
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"name": company_name,
				"company_name": company_name,
				"abbr": f"G{suffix[:4]}",
				"country": "Guatemala",
				"default_currency": "GTQ",
			}
		)
		company.db_insert()

		fiscal_year_name = f"GT-FY-{suffix}"
		frappe.get_doc(
			{
				"doctype": "Fiscal Year",
				"name": fiscal_year_name,
				"year": fiscal_year_name,
				"year_start_date": "2026-01-01",
				"year_end_date": "2026-12-31",
				"disabled": 0,
			}
		).db_insert()

		root_types = {
			"Activos": "Asset",
			"Pasivos": "Liability",
			"Patrimonio": "Equity",
			"Ingresos": "Income",
			"Costos": "Expense",
			"Gastos": "Expense",
		}
		accounts = {}
		for index, (account_name, root_type) in enumerate(root_types.items(), start=1):
			account = frappe.get_doc(
				{
					"doctype": "Account",
					"name": f"{account_name} - {company.abbr}",
					"account_name": account_name,
					"account_number": str(index),
					"company": company_name,
					"root_type": root_type,
					"report_type": "Profit and Loss"
					if root_type in {"Income", "Expense"}
					else "Balance Sheet",
					"is_group": 1,
					"lft": index * 2 - 1,
					"rgt": index * 2,
				}
			)
			account.db_insert()
			accounts[root_type] = account.name

		for index, values in enumerate((("Asset", 25, 0), ("Liability", 0, 25)), start=1):
			root_type, debit, credit = values
			frappe.get_doc(
				{
					"doctype": "GL Entry",
					"name": f"GT-GLE-{suffix}-{index}",
					"company": company_name,
					"posting_date": "2026-06-30",
					"account": accounts[root_type],
					"account_currency": "GTQ",
					"debit": debit,
					"credit": credit,
					"debit_in_account_currency": debit,
					"credit_in_account_currency": credit,
					"voucher_type": "Journal Entry",
					"voucher_no": f"GT-JV-{suffix}",
					"is_opening": "No",
					"is_cancelled": 0,
					"remarks": "Partida de integración",
				}
			).db_insert()

		# A deliberately unbalanced row in another finance book proves that
		# preflight, reconciliation and exports all validate the same closed scope.
		finance_book = frappe.get_doc(
			{
				"doctype": "Finance Book",
				"finance_book_name": f"GT Alternate {suffix}",
			}
		).insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": "GL Entry",
				"name": f"GT-OTHER-FB-{suffix}",
				"company": company_name,
				"posting_date": "2026-06-30",
				"account": accounts["Asset"],
				"account_currency": "GTQ",
				"debit": 99,
				"debit_in_account_currency": 99,
				"credit": 0,
				"credit_in_account_currency": 0,
				"voucher_type": "Journal Entry",
				"voucher_no": f"GT-OTHER-JV-{suffix}",
				"finance_book": finance_book.name,
				"is_opening": "No",
				"is_cancelled": 0,
				"remarks": "Fuera del alcance del libro financiero",
			}
		).db_insert()

		profile = frappe.get_doc(
			{
				"doctype": "ContaNext Tax Profile",
				"company": company_name,
				"nit": f"{frappe.utils.now_datetime().strftime('%H%M%S%f')[-10:]}-K",
				"legal_name": company_name,
				"tax_address": "Ciudad de Guatemala",
				"fiscal_name_for_books": company_name,
				"fiscal_establishment": "1",
				"accounting_framework": "NIIF para PYMES",
				"book_currency": "GTQ",
				"book_language": "Español",
				"fiscal_year_start_month": 1,
				"legal_representative_name": "Representante de prueba",
				"legal_representative_id": "ID-PRUEBA",
				"accountant_name": "Contador de prueba",
				"accountant_nit": "1234567-K",
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "GT Accounting Book Settings",
				"company": company_name,
				"tax_profile": profile.name,
				"enabled": 1,
				"book_currency": "GTQ",
				"language": "Español",
				"time_zone": "America/Guatemala",
				"page_size": "Carta",
				"orientation_policy": "Según tipo de libro",
				"require_period_closed": 0,
			}
		).insert()
		assessment = assess_existing_company(company_name)
		self.assertEqual(assessment["blocking_failures"], 0)
		self.assertEqual(assessment["manual_reviews"], 1)
		self.assertTrue(assessment["dry_run"])
		previous_run = frappe.get_doc(
			{
				"doctype": "GT Accounting Book Run",
				"name": f"GT-BK-PREV-{suffix}",
				"company": company_name,
				"book_type": "JOURNAL",
				"period_from": "2026-01-01",
				"period_to": "2026-12-31",
				"fiscal_year": fiscal_year_name,
				"currency": "GTQ",
				"generation_mode": "Technical Draft",
				"draft_notice": UNAUTHORIZED_DRAFT_LABEL,
				"status": "Sealed",
				"generation_number": 1,
				"preflight_status": "Passed",
				"prepared_by": "Administrator",
			}
		)
		previous_run.db_insert()
		private_file_url = f"/private/files/gt-evidence-{suffix}.pdf"
		frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"gt-evidence-{suffix}.pdf",
				"file_url": private_file_url,
				"is_private": 1,
			}
		).db_insert()
		evidence = frappe.get_doc(
			{
				"doctype": "GT Book Authorization Evidence",
				"company": company_name,
				"authority": "SAT",
				"book_type": "JOURNAL",
				"mode": "Computarizado",
				"status": "Draft",
				"resolution_number": f"TEST-{suffix}",
				"resolution_date": "2026-01-01",
				"resolution_file": private_file_url,
				"quantity_as_stated": "100",
				"unit_as_stated": "Sin interpretar",
			}
		).insert()
		book_run = frappe.get_doc(
			{
				"doctype": "GT Accounting Book Run",
				"company": company_name,
				"book_type": "JOURNAL",
				"period_from": "2026-01-01",
				"period_to": "2026-12-31",
				"fiscal_year": fiscal_year_name,
				"currency": "GTQ",
				"supersedes": previous_run.name,
				"correction_reason": "Corrección técnica de integración",
				"authorizations": [{"authorization_evidence": evidence.name}],
			}
		).insert()
		self.assertIn('"accounting_framework":"NIIF para PYMES"', book_run.tax_identity_snapshot)
		self.assertIn('"name":"Contador de prueba"', book_run.accountant_snapshot)
		self.assertIn('"identification":"ID-PRUEBA"', book_run.representative_snapshot)

		result = execute_preflight(book_run)
		self.assertEqual(result["status"], "Passed")
		self.assertEqual(result["blocking_failures"], 0)
		self.assertEqual(result["checks"], 12)
		book_run.reload()
		book_run.supersedes = None
		with self.assertRaises(frappe.ValidationError):
			book_run.save()
		book_run.reload()

		_, standard_gl = general_ledger_execute(
			frappe._dict(
				{
					"company": company_name,
					"from_date": frappe.utils.getdate("2026-01-01"),
					"to_date": frappe.utils.getdate("2026-12-31"),
					"categorize_by": "Categorize by Voucher",
					"include_default_book_entries": 0,
					"show_cancelled_entries": 0,
					"show_remarks": 1,
				}
			)
		)
		standard_entries = [row for row in standard_gl if row.get("gl_entry", "").startswith("GT-GLE-")]
		self.assertEqual(sum(flt(row.debit) for row in standard_entries), 25)
		self.assertEqual(sum(flt(row.credit) for row in standard_entries), 25)

		_, standard_trial = trial_balance_execute(
			frappe._dict(
				{
					"company": company_name,
					"fiscal_year": fiscal_year_name,
					"from_date": frappe.utils.getdate("2026-01-01"),
					"to_date": frappe.utils.getdate("2026-12-31"),
					"show_unclosed_fy_pl_balances": 1,
					"with_period_closing_entry_for_current_period": 1,
					"with_period_closing_entry_for_opening": 1,
					"show_zero_values": 1,
					"show_group_accounts": 1,
					"show_net_values": 0,
					"include_default_book_entries": 0,
					"cost_center": [],
					"project": [],
				}
			)
		)
		trial_by_account = {
			row["account"]: row for row in standard_trial if row.get("account") in accounts.values()
		}
		self.assertEqual(flt(trial_by_account[accounts["Asset"]]["debit"]), 25)
		self.assertEqual(flt(trial_by_account[accounts["Liability"]]["credit"]), 25)

		generation_key = frappe.generate_hash(length=32)
		book_run.db_set("generation_key", generation_key, update_modified=False)
		book_run.db_set("status", "Queued")
		generated = generate_book_run(book_run.name, generation_key)
		self.assertEqual(generated["status"], "Generated")
		book_run.reload()
		self.assertEqual(book_run.status, "Generated")
		self.assertTrue(book_run.emission_sha256)
		self.assertEqual(book_run.generation_progress, 100)
		self.assertEqual(book_run.row_count, 2)
		self.assertEqual(
			{row.artifact_type for row in book_run.artifacts},
			{"SNAPSHOT_PART", "SNAPSHOT_MANIFEST", "CSV", "XLSX"},
		)
		for artifact in book_run.artifacts:
			self.assertEqual(frappe.db.get_value("File", {"file_url": artifact.file_url}, "is_private"), 1)

		artifact_urls = [artifact.file_url for artifact in book_run.artifacts]
		repeated = generate_book_run(book_run.name, generation_key)
		self.assertEqual(repeated, generated)
		book_run.reload()
		self.assertEqual([artifact.file_url for artifact in book_run.artifacts], artifact_urls)

		book_run.db_set("reviewed_by", "Administrator", update_modified=False)
		book_run.db_set("rejected_by", "Administrator", update_modified=False)
		book_run.db_set("rejection_reason", "Corregir presentación", update_modified=False)
		book_run.db_set("status", "Rejected")
		with patch("frappe.enqueue") as enqueue:
			regeneration = request_generation(book_run.name)
		self.assertEqual(regeneration["status"], "Queued")
		enqueue.assert_called_once()
		book_run.reload()
		self.assertEqual(book_run.generation_number, 2)
		self.assertIsNone(book_run.reviewed_by)
		self.assertIsNone(book_run.rejected_by)
		self.assertIsNone(book_run.rejection_reason)
		generated = generate_book_run(book_run.name, regeneration["generation_key"])
		self.assertEqual(generated["status"], "Generated")
		book_run.reload()

		sealing_key = frappe.generate_hash(length=32)
		book_run.db_set("status", "Approved")
		book_run.db_set("sealing_key", sealing_key, update_modified=False)
		book_run.db_set("status", "Sealing")
		sealed = seal_book_run(book_run.name, sealing_key, "Administrator")
		self.assertEqual(sealed["status"], "Awaiting Print Confirmation")
		book_run.reload()
		previous_run.reload()
		self.assertEqual(previous_run.status, "Sealed")
		self.assertTrue(book_run.pdf_sha256)
		self.assertTrue(book_run.folio_allocation)
		self.assertEqual(
			frappe.db.get_value("GT Book Folio Allocation", book_run.folio_allocation, "status"),
			"Reserved",
		)
		self.assertEqual(
			frappe.db.get_value("File", {"file_url": book_run.sealed_pdf}, "is_private"), 1
		)
		manifest_file = frappe.get_doc("File", {"file_url": book_run.seal_manifest_file})
		manifest_content = manifest_file.get_content()
		if isinstance(manifest_content, bytes):
			manifest_content = manifest_content.decode()
		self.assertTrue(verify_seal_manifest(frappe.parse_json(manifest_content)))

		frappe.get_doc("User", "Administrator").add_roles("GT Books Manager")
		frappe.clear_cache(user="Administrator")
		confirmed = confirm_print(
			book_run.name, frappe.generate_hash(length=32), success=1
		)
		self.assertEqual(confirmed["status"], "Sealed")
		book_run.reload()
		previous_run.reload()
		self.assertEqual(previous_run.status, "Superseded")
		self.assertEqual(
			frappe.db.count(
				"GT Book Review Event",
				{"book_run": previous_run.name, "action": "SUPERSEDED"},
			),
			1,
		)
		self.assertEqual(
			frappe.db.get_value("GT Book Folio Allocation", book_run.folio_allocation, "status"),
			"Consumed",
		)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc("File", {"file_url": book_run.sealed_pdf}).delete()

		package = frappe.get_doc(
			{
				"doctype": "GT Requirement Package",
				"company": company_name,
				"request_reference": f"REQ-{suffix}",
				"period_from": "2026-01-01",
				"period_to": "2026-12-31",
				"purpose": "Prueba controlada",
				"recipient": "Auditor de prueba",
				"book_runs": [
					{
						"book_run": book_run.name,
						"include_pdf": 1,
						"include_csv": 1,
						"include_manifest": 1,
					}
				],
				"support_index": [
					{"document_type": "DTE", "reference": f"DTE-{suffix}"},
				],
			}
		).insert(ignore_permissions=True)
		package_result = generate_requirement_package(package.name)
		self.assertEqual(package_result["status"], "Generated")
		package.reload()
		self.assertEqual(frappe.db.get_value("File", {"file_url": package.package_file}, "is_private"), 1)
		self.assertTrue(package.package_sha256)
		self.assertEqual(release(package.name)["status"], "Released")
		audit_package_download(package.name)
		self.assertEqual(
			frappe.db.count("GT Requirement Package Event", {"requirement_package": package.name}),
			3,
		)
