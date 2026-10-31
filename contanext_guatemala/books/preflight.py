import json
from collections.abc import Callable
from decimal import Decimal

import frappe
from frappe.query_builder.functions import Sum
from frappe.utils import getdate, now_datetime

from contanext_guatemala.books.catalog import diagnose_company_catalog
from contanext_guatemala.books.gl import apply_finance_book
from contanext_guatemala.books.inventory import load_physical_counts, reconcile_inventory, stock_integrity_issues
from contanext_guatemala.books.reconciliation import reconcile_gl
from contanext_guatemala.books.types import CheckResult
from contanext_guatemala.fiscal.company import get_company_fiscal_configuration
from contanext_guatemala.validation import is_valid_nit_format


Check = Callable[[object], list[CheckResult]]


def execute_preflight(book_run) -> dict:
	results: list[CheckResult] = []
	for check in CHECKS:
		try:
			results.extend(check(book_run))
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Preflight {check.__name__}: {book_run.name}")
			results.append(
				CheckResult(
					code=f"{check.__name__.upper()}_FAILED",
					category="SECURITY",
					severity="BLOCKER",
					status="FAIL",
					message="El control no pudo completarse; revise el diagnóstico interno.",
				)
			)

	book_run.set("validation_results", [])
	for result in results:
		book_run.append(
			"validation_results",
			{
				"check_code": result.code,
				"category": result.category,
				"severity": result.severity,
				"status": result.status,
				"message": result.message,
				"evidence_json": json.dumps(
					result.evidence,
					ensure_ascii=False,
					separators=(",", ":"),
					sort_keys=True,
				),
			},
		)
	blocked = any(result.blocks for result in results)
	book_run.preflight_status = "Failed" if blocked else "Passed"
	book_run.preflight_at = now_datetime()
	book_run.save()
	return {
		"status": book_run.preflight_status,
		"checks": len(results),
		"blocking_failures": sum(result.blocks for result in results),
	}


def check_configuration(book_run) -> list[CheckResult]:
	settings = frappe.db.get_value(
		"GT Accounting Book Settings",
		{"company": book_run.company},
		["name", "enabled", "book_currency", "language"],
		as_dict=True,
	)
	passed = bool(settings and settings.enabled)
	return [
		CheckResult(
			"GT_SETTINGS_ENABLED",
			"FORMAT",
			"BLOCKER",
			"PASS" if passed else "FAIL",
			"Configuración de borradores habilitada."
			if passed
			else "La configuración de libros no existe o está deshabilitada.",
			{"settings": settings.name if settings else None},
		)
	]


def check_tax_identity(book_run) -> list[CheckResult]:
	configuration = get_company_fiscal_configuration(book_run.company)
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
	missing = [label for fieldname, label in required.items() if not getattr(configuration, fieldname)]
	invalid = []
	if configuration.nit and not is_valid_nit_format(configuration.nit):
		invalid.append("NIT")
	if configuration.accountant_nit and not is_valid_nit_format(configuration.accountant_nit):
		invalid.append("NIT del contador")
	if configuration.country != "Guatemala":
		invalid.append("País Guatemala")
	if configuration.currency != "GTQ":
		invalid.append("Moneda GTQ")
	passed = not missing and not invalid
	return [
		CheckResult(
			"GT_TAX_IDENTITY",
			"TAX",
			"BLOCKER",
			"PASS" if passed else "FAIL",
			"La identidad fiscal para libros está completa."
			if passed
			else "La configuración fiscal de la empresa está incompleta o contiene valores inválidos.",
			{
				"company": configuration.company,
				"address": configuration.fiscal_address_name,
				"missing_fields": missing,
				"invalid_fields": invalid,
			},
		)
	]


def check_localization(book_run) -> list[CheckResult]:
	company_currency = frappe.db.get_value("Company", book_run.company, "default_currency")
	settings = frappe.db.get_value(
		"GT Accounting Book Settings",
		{"company": book_run.company},
		["book_currency", "language", "time_zone"],
		as_dict=True,
	)
	passed = bool(
		settings
		and company_currency == "GTQ"
		and settings.book_currency == "GTQ"
		and settings.language == "Español"
		and settings.time_zone == "America/Guatemala"
	)
	return [
		CheckResult(
			"GT_LOCALIZATION",
			"FORMAT",
			"BLOCKER",
			"PASS" if passed else "FAIL",
			"Moneda, idioma y zona horaria corresponden a Guatemala."
			if passed
			else "La empresa o configuración no usa GTQ, Español y America/Guatemala.",
			{"company_currency": company_currency},
		)
	]


def check_fiscal_period(book_run) -> list[CheckResult]:
	fiscal_year = frappe.db.get_value(
		"Fiscal Year",
		book_run.fiscal_year,
		["year_start_date", "year_end_date", "disabled"],
		as_dict=True,
	)
	passed = bool(
		fiscal_year
		and not fiscal_year.disabled
		and getdate(fiscal_year.year_start_date) <= getdate(book_run.period_from)
		and getdate(fiscal_year.year_end_date) >= getdate(book_run.period_to)
	)
	return [
		CheckResult(
			"FISCAL_PERIOD",
			"ACCOUNTING",
			"BLOCKER",
			"PASS" if passed else "FAIL",
			"El período está contenido en un ejercicio fiscal activo."
			if passed
			else "El período no está contenido en el ejercicio fiscal seleccionado.",
		)
	]


def check_catalog(book_run) -> list[CheckResult]:
	findings = diagnose_company_catalog(book_run.company)
	blocking = [finding for finding in findings if finding.severity == "BLOCKER"]
	return [
		CheckResult(
			"ACCOUNT_CATALOG",
			"ACCOUNTING",
			"BLOCKER",
			"FAIL" if blocking else "PASS",
			"El catálogo tiene raíces, números y cuentas aptos para el prototipo."
			if not blocking
			else f"El catálogo tiene {len(blocking)} hallazgos bloqueantes.",
			{
				"finding_count": len(findings),
				"codes": sorted({finding.code for finding in findings}),
			},
		)
	]


def check_immutable_ledger(book_run) -> list[CheckResult]:
	enabled = bool(frappe.db.get_single_value("Accounts Settings", "enable_immutable_ledger"))
	return [
		CheckResult(
			"IMMUTABLE_LEDGER",
			"ACCOUNTING",
			"WARNING",
			"PASS" if enabled else "FAIL",
			"El libro mayor inmutable está habilitado."
			if enabled
			else "El libro mayor inmutable está deshabilitado; se registró el riesgo.",
			{"enabled": enabled},
		)
	]


def check_period_closed(book_run) -> list[CheckResult]:
	required = bool(
		frappe.db.get_value(
			"GT Accounting Book Settings", {"company": book_run.company}, "require_period_closed"
		)
	)
	if not required:
		return [
			CheckResult(
				"PERIOD_CLOSED", "ACCOUNTING", "INFO", "PASS", "La configuración no exige cierre."
			)
		]
	closing = frappe.db.exists(
		"Period Closing Voucher",
		{
			"company": book_run.company,
			"docstatus": 1,
			"period_start_date": ["<=", book_run.period_from],
			"period_end_date": [">=", book_run.period_to],
		},
	)
	return [
		CheckResult(
			"PERIOD_CLOSED",
			"ACCOUNTING",
			"BLOCKER",
			"PASS" if closing else "FAIL",
			"Existe un cierre sometido que cubre el período."
			if closing
			else "No existe un cierre sometido que cubra todo el período.",
			{"closing_voucher": closing},
		)
	]


def check_draft_journals(book_run) -> list[CheckResult]:
	count = frappe.db.count(
		"Journal Entry",
		{
			"company": book_run.company,
			"docstatus": 0,
			"posting_date": ["between", [book_run.period_from, book_run.period_to]],
		},
	)
	return [
		CheckResult(
			"DRAFT_JOURNAL_ENTRIES",
			"ACCOUNTING",
			"ERROR",
			"FAIL" if count else "PASS",
			f"Hay {count} asientos de diario en borrador dentro del período."
			if count
			else "No hay asientos de diario en borrador dentro del período.",
			{"count": count},
		)
	]


def check_balanced_vouchers(book_run) -> list[CheckResult]:
	gle = frappe.qb.DocType("GL Entry")
	query = (
		frappe.qb.from_(gle)
		.select(
			gle.voucher_type,
			gle.voucher_no,
			Sum(gle.debit).as_("debit"),
			Sum(gle.credit).as_("credit"),
		)
		.where(gle.company == book_run.company)
		.where(gle.posting_date.between(book_run.period_from, book_run.period_to))
		.where(gle.is_cancelled == 0)
		.groupby(gle.voucher_type, gle.voucher_no)
	)
	rows = apply_finance_book(query, gle, book_run.finance_book or None).run(as_dict=True)
	unbalanced = [
		row
		for row in rows
		if Decimal(str(row.debit or 0)) != Decimal(str(row.credit or 0))
	]
	return [
		CheckResult(
			"BALANCED_VOUCHERS",
			"ACCOUNTING",
			"BLOCKER",
			"FAIL" if unbalanced else "PASS",
			f"Hay {len(unbalanced)} comprobantes descuadrados."
			if unbalanced
			else "Todos los comprobantes contabilizados del período cuadran.",
			{"checked": len(rows), "unbalanced": len(unbalanced)},
		)
	]


def check_gl_reconciliation(book_run) -> list[CheckResult]:
	totals = reconcile_gl(
		book_run.company,
		book_run.period_from,
		book_run.period_to,
		book_run.finance_book or None,
	)
	return [
		CheckResult(
			"GL_RECONCILIATION",
			"ACCOUNTING",
			"BLOCKER",
			"PASS" if totals.reconciled else "FAIL",
			"Débitos, créditos y ecuación contable concilian en GL."
			if totals.reconciled
			else "GL no concilia en débitos/créditos o ecuación contable.",
			{
				"debit_credit_difference": str(totals.debit_credit_difference),
				"accounting_equation_difference": str(totals.accounting_equation_difference),
			},
		)
	]


def check_inventory_controls(book_run) -> list[CheckResult]:
	if book_run.book_type != "INVENTORY":
		return []
	from contanext_guatemala.books.types import BookScope

	physical_count = frappe.db.get_value(
		"GT Physical Count Import",
		book_run.physical_count_import,
		["company", "cutoff_date", "status", "accepted_rows", "rejected_rows", "file_sha256"],
		as_dict=True,
	) if book_run.physical_count_import else None
	count_valid = bool(
		physical_count
		and physical_count.company == book_run.company
		and physical_count.status == "Approved"
		and getdate(physical_count.cutoff_date) == getdate(book_run.period_to)
		and physical_count.accepted_rows
		and not physical_count.rejected_rows
	)
	results = [
		CheckResult(
			"PHYSICAL_COUNT_APPROVED",
			"INVENTORY",
			"BLOCKER",
			"PASS" if count_valid else "FAIL",
			"El conteo físico aprobado coincide con empresa y corte."
			if count_valid else "Falta un conteo físico aprobado, íntegro y correspondiente al corte.",
			{"import": book_run.physical_count_import, "sha256": physical_count.file_sha256 if physical_count else None},
		)
	]
	if not count_valid:
		return results
	scope = BookScope(
		company=book_run.company,
		period_from=getdate(book_run.period_from),
		period_to=getdate(book_run.period_to),
		fiscal_year=book_run.fiscal_year,
		finance_book=book_run.finance_book or None,
		currency=book_run.currency,
	)
	issues = stock_integrity_issues(scope, observed_at=book_run.creation, check_negative=False)
	reconciliation = reconcile_inventory(
		scope,
		physical_counts=load_physical_counts(book_run.physical_count_import),
	)
	issues["negative_balances"] = reconciliation.negative
	stable = not any(issues.values())
	results.append(
		CheckResult(
			"STOCK_CUTOFF_INTEGRITY",
			"INVENTORY",
			"BLOCKER",
			"PASS" if stable else "FAIL",
			"No hay inventario negativo, reposteo pendiente ni movimientos retroactivos."
			if stable else "El corte tiene inventario negativo, reposteo pendiente o actividad retroactiva.",
			issues,
		)
	)
	results.append(
		CheckResult(
			"INVENTORY_STOCK_GL_RECONCILIATION",
			"INVENTORY",
			"BLOCKER",
			"PASS" if reconciliation.reconciled else "FAIL",
			"Existencias, conteo físico y cuentas GL concilian sin tolerancia implícita."
			if reconciliation.reconciled else "Existencias, conteo físico o cuentas GL tienen diferencias bloqueantes.",
			{
				"stock_value": str(reconciliation.stock_value),
				"gl_value": str(reconciliation.gl_value),
				"value_difference": str(reconciliation.value_difference),
				"unmapped": reconciliation.unmapped,
				"ambiguous": reconciliation.ambiguous,
				"negative": reconciliation.negative,
				"physical_differences": reconciliation.physical_differences,
			},
		)
	)
	return results


def check_technical_only(book_run) -> list[CheckResult]:
	return [
		CheckResult(
			"TECHNICAL_DRAFT_ONLY",
			"AUTHORIZATION",
			"INFO",
			"PASS",
			"La emisión está limitada a borrador técnico y no consumirá folios.",
			{"mode": book_run.generation_mode},
		)
	]


CHECKS: tuple[Check, ...] = (
	check_configuration,
	check_tax_identity,
	check_localization,
	check_fiscal_period,
	check_catalog,
	check_immutable_ledger,
	check_period_closed,
	check_draft_journals,
	check_balanced_vouchers,
	check_gl_reconciliation,
	check_inventory_controls,
	check_technical_only,
)
