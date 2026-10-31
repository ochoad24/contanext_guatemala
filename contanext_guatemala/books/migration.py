from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from contanext_guatemala.books.snapshots import canonical_json, sha256_hex


MIGRATION_ASSESSMENT_SCHEMA = "contanext.gt.accounting-book.migration-assessment"
MIGRATION_ASSESSMENT_VERSION = 2


@dataclass(frozen=True, slots=True)
class MigrationCheck:
	code: str
	severity: str
	status: str
	message: str


def build_migration_assessment(
	company: str,
	*,
	country: str | None,
	currency: str | None,
	account_findings: Iterable[Mapping[str, Any]],
	fiscal_missing_fields: Iterable[str],
	fiscal_configuration_errors: Iterable[str] = (),
	settings_count: int,
	draft_transaction_count: int,
	gl_entry_count: int,
	stock_ledger_entry_count: int,
	book_run_count: int,
) -> dict[str, Any]:
	"""Build a deterministic, read-only migration assessment.

	The assessment deliberately never proposes edits to GL/SLE or business
	documents. Existing movements always require an approved, company-specific
	migration plan before books can be enabled.
	"""
	findings = [dict(finding) for finding in account_findings]
	fiscal_missing = list(fiscal_missing_fields)
	fiscal_errors = list(fiscal_configuration_errors)
	checks: list[MigrationCheck] = []
	checks.append(
		MigrationCheck(
			"GT_LOCALIZATION",
			"BLOCKER",
			"PASS" if country == "Guatemala" and currency == "GTQ" else "FAIL",
			"La empresa usa Guatemala y GTQ."
			if country == "Guatemala" and currency == "GTQ"
			else "La empresa debe revisarse: país Guatemala y moneda GTQ son obligatorios para este alcance.",
		)
	)
	checks.append(
		MigrationCheck(
			"ACCOUNT_CATALOG",
			"BLOCKER",
			"PASS" if not findings else "FAIL",
			"El catálogo no presenta hallazgos estructurales."
			if not findings
			else f"El catálogo presenta {len(findings)} hallazgo(s); no se modifica automáticamente.",
		)
	)
	checks.append(
		MigrationCheck(
			"FISCAL_CONFIGURATION",
			"BLOCKER",
			"PASS" if not fiscal_missing and not fiscal_errors else "FAIL",
			"La configuración fiscal de Company está completa para libros."
			if not fiscal_missing and not fiscal_errors
			else "La configuración fiscal de Company está incompleta o es inválida.",
		)
	)
	checks.append(
		MigrationCheck(
			"BOOK_SETTINGS",
			"BLOCKER",
			"PASS" if settings_count == 1 else "FAIL",
			"Existe una única configuración de libros."
			if settings_count == 1
			else "Debe existir exactamente una configuración de libros por empresa.",
		)
	)
	checks.append(
		MigrationCheck(
			"DRAFT_TRANSACTIONS",
			"BLOCKER",
			"PASS" if draft_transaction_count == 0 else "FAIL",
			"No se detectaron comprobantes contables relevantes en borrador."
			if draft_transaction_count == 0
			else f"Hay {draft_transaction_count} comprobante(s) relevante(s) en borrador.",
		)
	)
	movement_count = gl_entry_count + stock_ledger_entry_count
	checks.append(
		MigrationCheck(
			"EXISTING_MOVEMENTS",
			"REVIEW",
			"PASS" if movement_count == 0 else "REVIEW",
			"La empresa no tiene movimientos contables ni de inventario."
			if movement_count == 0
			else (
				f"Se detectaron {gl_entry_count} filas GL y {stock_ledger_entry_count} filas SLE; "
				"se requiere aprobación explícita del plan de incorporación."
			),
		)
	)
	checks.append(
		MigrationCheck(
			"PRIOR_BOOK_RUNS",
			"REVIEW",
			"PASS" if book_run_count == 0 else "REVIEW",
			"No existen emisiones previas."
			if book_run_count == 0
			else f"Existen {book_run_count} emisión(es); deben conservarse y revisarse antes de incorporar la empresa.",
		)
	)
	payload: dict[str, Any] = {
		"schema": MIGRATION_ASSESSMENT_SCHEMA,
		"version": MIGRATION_ASSESSMENT_VERSION,
		"company": company,
		"dry_run": True,
		"mutations_performed": [],
		"automatic_ledger_migration_allowed": False,
		"facts": {
			"country": country,
			"currency": currency,
			"fiscal_missing_fields": fiscal_missing,
			"fiscal_configuration_errors": fiscal_errors,
			"settings_count": settings_count,
			"draft_transaction_count": draft_transaction_count,
			"gl_entry_count": gl_entry_count,
			"stock_ledger_entry_count": stock_ledger_entry_count,
			"book_run_count": book_run_count,
			"catalog_finding_count": len(findings),
		},
		"catalog_findings": findings,
		"checks": [asdict(check) for check in checks],
	}
	payload["blocking_failures"] = sum(
		check.status == "FAIL" and check.severity == "BLOCKER" for check in checks
	)
	payload["manual_reviews"] = sum(check.status == "REVIEW" for check in checks)
	payload["assessment_sha256"] = sha256_hex(canonical_json(payload))
	return payload


def assess_existing_company(company: str) -> dict[str, Any]:
	"""Read ERPNext state without mutating masters, transactions or settings."""
	if not company:
		raise ValueError("La empresa es obligatoria.")
	import frappe

	from contanext_guatemala.books.catalog import diagnose_company_catalog
	from contanext_guatemala.fiscal.company import get_company_fiscal_configuration

	company_doc = frappe.get_doc("Company", company)
	company_doc.check_permission("read")
	findings = [asdict(finding) for finding in diagnose_company_catalog(company)]
	fiscal_missing = []
	fiscal_errors = []
	try:
		configuration = get_company_fiscal_configuration(company)
		required = {
			"legal_name": "Razón social",
			"nit": "NIT",
			"fiscal_address": "Dirección fiscal",
			"establishment_code": "Código de establecimiento fiscal",
			"accounting_framework": "Marco contable",
			"legal_representative_name": "Representante legal",
			"accountant_name": "Contador",
			"accountant_nit": "NIT del contador",
		}
		fiscal_missing = [
			label for fieldname, label in required.items() if not getattr(configuration, fieldname)
		]
	except frappe.ValidationError as exc:
		fiscal_errors = [str(exc)]
	draft_count = 0
	for doctype in ("Journal Entry", "Payment Entry", "Sales Invoice", "Purchase Invoice"):
		if frappe.db.exists("DocType", doctype):
			draft_count += frappe.db.count(doctype, {"company": company, "docstatus": 0})
	return build_migration_assessment(
		company,
		country=company_doc.country,
		currency=company_doc.default_currency,
		account_findings=findings,
		fiscal_missing_fields=fiscal_missing,
		fiscal_configuration_errors=fiscal_errors,
		settings_count=frappe.db.count("GT Accounting Book Settings", {"company": company}),
		draft_transaction_count=draft_count,
		gl_entry_count=frappe.db.count("GL Entry", {"company": company}),
		stock_ledger_entry_count=frappe.db.count("Stock Ledger Entry", {"company": company}),
		book_run_count=frappe.db.count("GT Accounting Book Run", {"company": company}),
	)
