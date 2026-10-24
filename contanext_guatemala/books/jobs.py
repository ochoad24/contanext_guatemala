import json
from dataclasses import asdict

from contanext_guatemala.books.constants import SNAPSHOT_VERSION
from contanext_guatemala.books.exports import csv_bytes, xlsx_bytes
from contanext_guatemala.books.financial_statements import (
	financial_statements_dataset,
	reconcile_financial_statements,
)
from contanext_guatemala.books.gl import account_catalog
from contanext_guatemala.books.journal import journal_dataset
from contanext_guatemala.books.inventory import (
	INVENTORY_COLUMNS,
	load_physical_counts,
	reconcile_inventory,
)
from contanext_guatemala.books.ledger import ledger_dataset
from contanext_guatemala.books.reconciliation import reconcile_base_books
from contanext_guatemala.books.snapshots import (
	build_manifest,
	canonical_json,
	emission_sha256,
	iter_snapshot_parts,
	iter_snapshot_rows,
	sha256_hex,
)
from contanext_guatemala.books.trial_balance import trial_balance_dataset
from contanext_guatemala.books.types import BookScope
from contanext_guatemala.books.upgrade_contract import SOURCE_ORDER_VERSION


DATASETS = {
	"JOURNAL": journal_dataset,
	"LEDGER": ledger_dataset,
	"TRIAL_BALANCE": trial_balance_dataset,
	"FINANCIAL_STATEMENTS": financial_statements_dataset,
}


def generate_book_run(book_run: str, generation_key: str) -> dict:
	import frappe

	lock = frappe.cache.lock(f"gt-book-generation:{book_run}", timeout=21_600)
	if not lock.acquire(blocking=False):
		return {"status": "Queued", "reason": "already_running"}
	try:
		return _generate_book_run(book_run, generation_key)
	finally:
		if lock.owned():
			lock.release()


def _generate_book_run(book_run: str, generation_key: str) -> dict:
	import frappe
	from frappe.utils import getdate, now_datetime

	doc = frappe.get_doc("GT Accounting Book Run", book_run)
	if doc.status == "Generated" and doc.generation_key == generation_key:
		return {"status": "Generated", "emission_sha256": doc.emission_sha256}
	if doc.status != "Queued" or doc.generation_key != generation_key:
		frappe.throw("La clave o el estado de generación ya no están vigentes.")

	try:
		from contanext_guatemala.books.preflight import execute_preflight

		_progress(doc, 10, "Revalidando preflight")
		preflight = execute_preflight(doc)
		if preflight["status"] != "Passed":
			_progress(doc, 100, "Preflight bloqueante")
			doc.db_set("status", "Validation Failed")
			return {"status": "Validation Failed", "reason": "preflight"}

		scope = BookScope(
			company=doc.company,
			period_from=getdate(doc.period_from),
			period_to=getdate(doc.period_to),
			fiscal_year=doc.fiscal_year,
			finance_book=doc.finance_book or None,
			currency=doc.currency,
		)
		_progress(doc, 30, "Conciliando Diario, Mayor y Balance")
		reconciliation = reconcile_base_books(scope)
		reconciliation_payload = _reconciliation_payload(reconciliation)
		if not reconciliation["reconciled"]:
			doc.db_set("reconciliation_json", _json(reconciliation_payload), update_modified=False)
			_progress(doc, 100, "Conciliación bloqueante")
			doc.db_set("status", "Validation Failed")
			return {"status": "Validation Failed", "reason": "reconciliation"}
		if doc.book_type == "FINANCIAL_STATEMENTS":
			financial_reconciliation = reconcile_financial_statements(scope)
			reconciliation_payload["financial_statements"] = asdict(financial_reconciliation) | {
				"period_result": financial_reconciliation.period_result,
				"balance_difference": financial_reconciliation.balance_difference,
				"reconciled": financial_reconciliation.reconciled,
			}
			if not financial_reconciliation.reconciled:
				doc.db_set("reconciliation_json", _json(reconciliation_payload), update_modified=False)
				_progress(doc, 100, "Estados financieros no conciliados")
				doc.db_set("status", "Validation Failed")
				return {"status": "Validation Failed", "reason": "financial_reconciliation"}
		inventory_reconciliation = None
		if doc.book_type == "INVENTORY":
			inventory_reconciliation = reconcile_inventory(
				scope,
				physical_counts=load_physical_counts(doc.physical_count_import),
			)
			reconciliation_payload["inventory"] = {
				"stock_value": inventory_reconciliation.stock_value,
				"gl_value": inventory_reconciliation.gl_value,
				"value_difference": inventory_reconciliation.value_difference,
				"unmapped": inventory_reconciliation.unmapped,
				"ambiguous": inventory_reconciliation.ambiguous,
				"negative": inventory_reconciliation.negative,
				"physical_differences": inventory_reconciliation.physical_differences,
				"reconciled": inventory_reconciliation.reconciled,
			}
			if not inventory_reconciliation.reconciled:
				doc.db_set("reconciliation_json", _json(reconciliation_payload), update_modified=False)
				_progress(doc, 100, "Inventario, conteo físico y GL no conciliados")
				doc.db_set("status", "Validation Failed")
				return {"status": "Validation Failed", "reason": "inventory_reconciliation"}

		_progress(doc, 50, "Construyendo snapshot canónico")
		if inventory_reconciliation:
			from contanext_guatemala.books.types import BookDataset

			dataset = BookDataset(columns=INVENTORY_COLUMNS, rows=iter(inventory_reconciliation.rows))
		else:
			dataset = DATASETS[doc.book_type](scope)
		metadata = _metadata(doc, scope, dataset.columns)
		parts = list(iter_snapshot_parts(dataset.rows))
		manifest = build_manifest(parts, metadata)
		sealable_parameters = {
			"book_run": doc.name,
			"book_type": doc.book_type,
			"generation_number": doc.generation_number,
			"generation_mode": doc.generation_mode,
			"draft_notice": doc.draft_notice,
		}
		emission_hash = emission_sha256(manifest, sealable_parameters)
		_progress(doc, 70, "Generando exportaciones")
		csv_content = csv_bytes(dataset.columns, iter_snapshot_rows(parts))
		xlsx_content = xlsx_bytes(
			dataset.columns,
			iter_snapshot_rows(parts),
			{
				"emision": doc.name,
				"tipo_libro": doc.book_type,
				"empresa": doc.company,
				"desde": str(doc.period_from),
				"hasta": str(doc.period_to),
				"moneda": doc.currency,
				"sha256_emision": emission_hash,
				"aviso": doc.draft_notice,
			},
		)
		_progress(doc, 85, "Guardando archivos privados")
		_store_artifacts(doc, parts, manifest, csv_content, xlsx_content)
		doc.generated_at = now_datetime()
		doc.row_count = manifest["row_count"]
		doc.emission_sha256 = emission_hash
		doc.reconciliation_json = _json(reconciliation_payload)
		doc.snapshot_manifest = canonical_json(manifest).decode("utf-8")
		doc.generation_progress = 100
		doc.generation_message = "Generación completada"
		doc.save(ignore_permissions=True)
		doc.db_set("status", "Generated")
		return {"status": "Generated", "emission_sha256": emission_hash}
	except Exception:
		if frappe.db.get_value("GT Accounting Book Run", book_run, "status") == "Queued":
			frappe.db.set_value("GT Accounting Book Run", book_run, "status", "Validation Failed")
			frappe.db.set_value(
				"GT Accounting Book Run", book_run, "generation_message", "La generación falló"
			)
		frappe.log_error(title=f"Generación de libro GT: {book_run}", message=frappe.get_traceback())
		raise


def _metadata(doc, scope: BookScope, columns: tuple[str, ...]) -> dict:
	import erpnext
	import frappe
	import contanext_guatemala

	return {
		"book_run": doc.name,
		"book_type": doc.book_type,
		"company": scope.company,
		"period_from": scope.period_from,
		"period_to": scope.period_to,
		"fiscal_year": scope.fiscal_year,
		"finance_book": scope.finance_book,
		"currency": scope.currency,
		"columns": list(columns),
		"source_order_version": SOURCE_ORDER_VERSION,
		"snapshot_version": SNAPSHOT_VERSION,
		"versions": {
			"frappe": getattr(frappe, "__version__", "unknown"),
			"erpnext": getattr(erpnext, "__version__", "unknown"),
			"contanext_guatemala": getattr(contanext_guatemala, "__version__", "unknown"),
		},
		"tax_identity": json.loads(doc.tax_identity_snapshot or "{}"),
		"account_catalog": account_catalog(scope),
		"accounting_framework": json.loads(doc.tax_identity_snapshot or "{}").get("accounting_framework"),
		"annexes": _annex_metadata(doc),
		"physical_count": _physical_count_metadata(doc),
	}


def _annex_metadata(doc) -> list[dict]:
	return [
		{
			"annex": row.annex,
			"order": row.display_order,
			"title": row.title_snapshot,
			"type": row.annex_type_snapshot,
			"version": row.version_snapshot,
			"file_url": row.file_url_snapshot,
			"sha256": row.sha256_snapshot,
			"approved_by": row.approved_by_snapshot,
			"approved_at": row.approved_at_snapshot,
		}
		for row in sorted(doc.annexes, key=lambda item: (item.display_order, item.annex))
	]


def _physical_count_metadata(doc) -> dict | None:
	if doc.book_type != "INVENTORY" or not doc.physical_count_import:
		return None
	import frappe

	value = frappe.db.get_value(
		"GT Physical Count Import",
		doc.physical_count_import,
		["name", "cutoff_date", "template_version", "source_file", "file_sha256", "accepted_rows", "approved_by", "approved_at", "stock_reconciliation"],
		as_dict=True,
	)
	return dict(value) if value else None


def _store_artifacts(doc, parts, manifest, csv_content: bytes, xlsx_content: bytes) -> None:
	from frappe.utils.file_manager import save_file

	doc.set("artifacts", [])
	for part in parts:
		file_doc = save_file(
			f"{doc.name}-snapshot-{part.index:05d}.jsonl.gz",
			part.content,
			doc.doctype,
			doc.name,
			is_private=True,
		)
		stored_content = _stored_file_bytes(file_doc)
		if sha256_hex(stored_content) != part.sha256:
			raise RuntimeError("Frappe alteró una parte canónica del snapshot al almacenarla.")
		doc.append(
			"artifacts",
			{
				"artifact_type": "SNAPSHOT_PART",
				"part_index": part.index,
				"file_url": file_doc.file_url,
				"content_type": "application/gzip",
				"row_count": part.row_count,
				"sha256": sha256_hex(stored_content),
			},
		)
	for artifact_type, extension, content_type, content, row_count in (
		("SNAPSHOT_MANIFEST", "manifest.json", "application/json", canonical_json(manifest), 0),
		("CSV", "csv", "text/csv; charset=utf-8", csv_content, manifest["row_count"]),
		(
			"XLSX",
			"xlsx",
			"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
			xlsx_content,
			manifest["row_count"],
		),
	):
		file_doc = save_file(
			f"{doc.name}-{extension}", content, doc.doctype, doc.name, is_private=True
		)
		stored_content = _stored_file_bytes(file_doc)
		doc.append(
			"artifacts",
			{
				"artifact_type": artifact_type,
				"file_url": file_doc.file_url,
				"content_type": content_type,
				"row_count": row_count,
				"sha256": sha256_hex(stored_content),
			},
		)
	for annex in sorted(doc.annexes, key=lambda item: (item.display_order, item.annex)):
		doc.append(
			"artifacts",
			{
				"artifact_type": "ANNEX_PDF",
				"part_index": annex.display_order,
				"file_url": annex.file_url_snapshot,
				"content_type": "application/pdf",
				"row_count": 0,
				"sha256": annex.sha256_snapshot,
			},
		)


def _stored_file_bytes(file_doc) -> bytes:
	content = file_doc.get_content()
	return content.encode("utf-8") if isinstance(content, str) else content


def _reconciliation_payload(value: dict) -> dict:
	return {
		"journal": asdict(value["journal"]),
		"ledger": asdict(value["ledger"]),
		"trial_balance": asdict(value["trial_balance"]),
		"debit_difference": value["debit_difference"],
		"credit_difference": value["credit_difference"],
		"reconciled": value["reconciled"],
	}


def _json(value: dict) -> str:
	return canonical_json(value).decode("utf-8")


def _progress(doc, percent: int, message: str) -> None:
	doc.db_set("generation_progress", percent, update_modified=False)
	doc.db_set("generation_message", message, update_modified=False)
