import gzip
import hashlib
import io
import json
import platform
import time
import tracemalloc
import zipfile
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime
from typing import Any

from contanext_guatemala.books.manifests import verify_seal_bundle
from contanext_guatemala.books.requirements import verify_requirement_zip
from contanext_guatemala.books.snapshots import (
	canonical_json,
	emission_sha256,
	sha256_hex,
	verify_manifest,
)


VERIFICATION_SCHEMA = "contanext.gt.accounting-books.operational-verification"
VERIFICATION_VERSION = 1
BENCHMARK_SCHEMA = "contanext.gt.accounting-books.performance-benchmark"
BENCHMARK_VERSION = 1


def measure_iterable(
	label: str,
	rows: Iterable[Mapping[str, Any]],
	*,
	source_count: Callable[[], int] | None = None,
) -> dict[str, Any]:
	"""Consume a pipeline and report time, Python peak memory and a content fingerprint."""
	started_tracing = not tracemalloc.is_tracing()
	if started_tracing:
		tracemalloc.start()
	tracemalloc.reset_peak()
	started = time.perf_counter()
	count = 0
	digest = hashlib.sha256()
	try:
		for row in rows:
			count += 1
			digest.update(canonical_json(_safe_benchmark_value(dict(row))))
			digest.update(b"\n")
		elapsed = time.perf_counter() - started
		_, peak = tracemalloc.get_traced_memory()
	finally:
		if started_tracing:
			tracemalloc.stop()
	payload = {
		"label": label,
		"source_rows": source_count() if source_count else count,
		"result_rows": count,
		"elapsed_seconds": f"{elapsed:.6f}",
		"peak_python_bytes": peak,
		"content_sha256": digest.hexdigest(),
	}
	return payload


def build_benchmark_report(
	*,
	scope: Mapping[str, Any],
	measurements: Iterable[Mapping[str, Any]],
	environment: Mapping[str, Any],
	approved_budgets: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
	budgets = dict(approved_budgets or {})
	items = []
	for source in measurements:
		item = dict(source)
		budget = budgets.get(str(item.get("label")))
		item["budget"] = _safe_benchmark_value(dict(budget)) if budget else None
		item["budget_status"] = _budget_status(item, budget)
		items.append(item)
	report = {
		"schema": BENCHMARK_SCHEMA,
		"version": BENCHMARK_VERSION,
		"scope": dict(scope),
		"environment": dict(environment),
		"measurements": items,
		"notice": "MEDICIÓN TÉCNICA; G12 permanece abierta hasta aprobar y cumplir presupuestos.",
	}
	report["report_sha256"] = sha256_hex(canonical_json(_safe_benchmark_value(report)))
	return report


def verify_review_event_chain(events: Iterable[Mapping[str, Any]]) -> bool:
	previous = ""
	for source in events:
		event = dict(source)
		try:
			artifacts = json.loads(event.get("artifact_snapshot_json") or "[]")
			payload = {
				"book_run": event.get("book_run"),
				"company": event.get("company"),
				"action": event.get("action"),
				"actor": event.get("actor"),
				"event_at": str(event.get("event_at")),
				"comment": event.get("comment"),
				"emission_sha256": event.get("emission_sha256"),
				"artifacts": artifacts,
				"previous_event_sha256": previous,
			}
			if event.get("previous_event_sha256") != previous:
				return False
			if event.get("event_sha256") != sha256_hex(canonical_json(payload)):
				return False
		except (TypeError, ValueError, json.JSONDecodeError):
			return False
		previous = event["event_sha256"]
	return True


def verify_folio_event_chain(events: Iterable[Mapping[str, Any]]) -> bool:
	previous = ""
	for source in events:
		event = dict(source)
		try:
			failed_pages = json.loads(event.get("failed_pages_json") or "[]")
			payload = {
				"allocation": event.get("allocation"),
				"book_run": event.get("book_run"),
				"action": event.get("action"),
				"actor": event.get("actor"),
				"event_at": str(event.get("event_at")),
				"idempotency_key": event.get("idempotency_key"),
				"failed_pages": failed_pages,
				"reason": event.get("reason"),
				"previous_event_sha256": previous,
			}
			if event.get("previous_event_sha256") != previous:
				return False
			if event.get("event_sha256") != sha256_hex(canonical_json(payload)):
				return False
		except (TypeError, ValueError, json.JSONDecodeError):
			return False
		previous = event["event_sha256"]
	return True


def run_performance_benchmark(
	company: str,
	period_from: str,
	period_to: str,
	fiscal_year: str,
	finance_book: str | None = None,
	page_size: int = 5_000,
	approved_budgets: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
	"""Run read-only GL and SLE pipelines on a prepared benchmark site."""
	import erpnext
	import frappe
	import contanext_guatemala
	from frappe.utils import getdate

	from contanext_guatemala.books.inventory import collapse_sle_rows, iter_sle_rows
	from contanext_guatemala.books.journal import iter_journal_rows
	from contanext_guatemala.books.types import BookScope
	from contanext_guatemala.books.upgrade_contract import SOURCE_ORDER_VERSION

	if not frappe.db.exists("Company", company):
		raise ValueError("La empresa del benchmark no existe.")
	if page_size < 1:
		raise ValueError("page_size debe ser positivo.")
	scope = BookScope(
		company=company,
		period_from=getdate(period_from),
		period_to=getdate(period_to),
		fiscal_year=fiscal_year,
		finance_book=finance_book,
	)
	if scope.period_from > scope.period_to:
		raise ValueError("El período del benchmark es inválido.")
	journal = measure_iterable("GL_JOURNAL", iter_journal_rows(scope, page_size=page_size))
	stock_source = _CountingRows(iter_sle_rows(scope, page_size=page_size))
	stock = measure_iterable(
		"SLE_CLOSING_BALANCES",
		collapse_sle_rows(stock_source),
		source_count=lambda: stock_source.count,
	)
	return build_benchmark_report(
		scope={
			"company": company,
			"period_from": scope.period_from,
			"period_to": scope.period_to,
			"fiscal_year": fiscal_year,
			"finance_book": finance_book,
			"page_size": page_size,
		},
		measurements=(journal, stock),
		environment={
			"python": platform.python_version(),
			"frappe": getattr(frappe, "__version__", "unknown"),
			"erpnext": getattr(erpnext, "__version__", "unknown"),
			"contanext_guatemala": getattr(contanext_guatemala, "__version__", "unknown"),
			"source_order_version": SOURCE_ORDER_VERSION,
		},
		approved_budgets=approved_budgets,
	)


def verify_restored_books(company: str | None = None) -> dict[str, Any]:
	"""Verify restored accounting-book records and private files without mutating them."""
	import frappe

	failures: list[dict[str, str]] = []
	run_filters = {"company": company} if company else None
	run_names = frappe.get_all("GT Accounting Book Run", filters=run_filters, pluck="name", order_by="name asc")
	verified_artifacts = 0
	for name in run_names:
		try:
			verified_artifacts += _verify_restored_run(frappe.get_doc("GT Accounting Book Run", name))
		except Exception as exc:
			failures.append({"object_type": "GT Accounting Book Run", "object": name, "reason": str(exc)})

	package_filters = {"company": company, "status": ["in", ["Generated", "Released"]]} if company else {
		"status": ["in", ["Generated", "Released"]]
	}
	package_names = frappe.get_all(
		"GT Requirement Package",
		filters=package_filters,
		pluck="name",
		order_by="name asc",
	)
	for name in package_names:
		try:
			doc = frappe.get_doc("GT Requirement Package", name)
			content = _private_file_bytes(doc.package_file)
			if sha256_hex(content) != doc.package_sha256 or not verify_requirement_zip(content):
				raise ValueError("El ZIP o su hash no es verificable.")
			if _requirement_manifest_hash(content) != doc.manifest_sha256:
				raise ValueError("El manifiesto del ZIP no coincide con el registro restaurado.")
		except Exception as exc:
			failures.append({"object_type": "GT Requirement Package", "object": name, "reason": str(exc)})

	counts = {}
	for doctype in (
		"GT Accounting Book Run",
		"GT Book Operational Alert",
		"GT Requirement Package",
		"GT Book Review Event",
		"GT Book Folio Event",
		"GT Requirement Package Event",
	):
		filters = {"company": company} if company else None
		counts[doctype] = frappe.db.count(doctype, filters=filters)
	report = {
		"schema": VERIFICATION_SCHEMA,
		"version": VERIFICATION_VERSION,
		"site": frappe.local.site,
		"company": company,
		"counts": counts,
		"verified_artifacts": verified_artifacts,
		"verified_packages": len(package_names) - sum(
			1 for item in failures if item["object_type"] == "GT Requirement Package"
		),
		"failures": failures,
		"passed": not failures,
		"notice": "EVIDENCIA DE SITIO RESTAURADO; no cierra G14 sin acta operativa, RPO/RTO y prueba de permisos.",
	}
	report["report_sha256"] = sha256_hex(canonical_json(report))
	return report


def _verify_restored_run(doc) -> int:
	import frappe

	contents: dict[str, bytes] = {}
	artifacts: dict[tuple[str, int], Any] = {}
	for artifact in doc.artifacts:
		content = _private_file_bytes(artifact.file_url)
		if sha256_hex(content) != artifact.sha256:
			raise ValueError(f"Hash de artefacto inválido: {artifact.artifact_type}.")
		contents[artifact.file_url] = content
		artifacts[(artifact.artifact_type, int(artifact.part_index or 0))] = artifact

	if doc.snapshot_manifest:
		manifest = json.loads(doc.snapshot_manifest)
		if not verify_manifest(manifest):
			raise ValueError("El manifiesto de snapshot no es verificable.")
		manifest_artifact = artifacts.get(("SNAPSHOT_MANIFEST", 0))
		if not manifest_artifact or json.loads(contents[manifest_artifact.file_url]) != manifest:
			raise ValueError("El archivo de manifiesto no coincide con la emisión restaurada.")
		for part in manifest["parts"]:
			artifact = artifacts.get(("SNAPSHOT_PART", int(part["index"])))
			if not artifact or artifact.sha256 != part["sha256"] or artifact.row_count != part["row_count"]:
				raise ValueError("Una parte de snapshot no coincide con el manifiesto.")
			if len(gzip.decompress(contents[artifact.file_url]).splitlines()) != part["row_count"]:
				raise ValueError("El conteo físico de una parte de snapshot es inválido.")
		parameters = {
			"book_run": doc.name,
			"book_type": doc.book_type,
			"generation_number": doc.generation_number,
			"generation_mode": doc.generation_mode,
			"draft_notice": doc.draft_notice,
		}
		if emission_sha256(manifest, parameters) != doc.emission_sha256:
			raise ValueError("El hash de emisión no coincide con el snapshot restaurado.")

	if doc.seal_manifest_file:
		seal_manifest = json.loads(_private_file_bytes(doc.seal_manifest_file))
		if seal_manifest.get("manifest_sha256") != doc.seal_manifest_sha256:
			raise ValueError("El hash registrado del manifiesto de sellado no coincide.")
		if not verify_seal_bundle(seal_manifest, contents):
			raise ValueError("El paquete de sellado restaurado no es verificable.")

	review_events = frappe.get_all(
		"GT Book Review Event",
		filters={"book_run": doc.name},
		fields=["*"],
		order_by="event_at asc, creation asc",
	)
	reviewed_statuses = {
		"Approved",
		"Sealing",
		"Awaiting Print Confirmation",
		"Print Exception",
		"Sealed",
		"Superseded",
	}
	if doc.status in reviewed_statuses and not review_events:
		raise ValueError("La emisión aprobada o sellada no conserva eventos de revisión.")
	if not verify_review_event_chain(review_events):
		raise ValueError("La cadena de eventos de revisión es inválida.")
	folio_events = frappe.get_all(
		"GT Book Folio Event",
		filters={"book_run": doc.name},
		fields=["*"],
		order_by="event_at asc, creation asc",
	)
	if doc.folio_allocation and not folio_events:
		raise ValueError("La reserva de folios no conserva eventos.")
	if not verify_folio_event_chain(folio_events):
		raise ValueError("La cadena de eventos de folios es inválida.")
	return len(doc.artifacts)


def _private_file_bytes(file_url: str) -> bytes:
	import frappe

	if not file_url:
		raise ValueError("Falta la referencia al archivo privado.")
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	if not file_doc.is_private:
		raise ValueError("Un archivo controlado fue restaurado como público.")
	content = file_doc.get_content()
	return content.encode("utf-8") if isinstance(content, str) else content


def _budget_status(measurement: Mapping[str, Any], budget: Mapping[str, Any] | None) -> str:
	if not budget:
		return "NOT_APPROVED"
	checks = (
		float(measurement.get("elapsed_seconds", 0)) <= float(budget.get("max_seconds", float("inf"))),
		int(measurement.get("peak_python_bytes", 0))
		<= int(budget.get("max_peak_python_bytes", 2**63 - 1)),
		int(measurement.get("source_rows", 0)) >= int(budget.get("min_source_rows", 0)),
	)
	return "PASSED" if all(checks) else "FAILED"


def _safe_benchmark_value(value: Any) -> Any:
	if isinstance(value, Mapping):
		return {str(key): _safe_benchmark_value(item) for key, item in value.items()}
	if isinstance(value, (list, tuple)):
		return [_safe_benchmark_value(item) for item in value]
	if isinstance(value, datetime):
		return str(value)
	if isinstance(value, float):
		return format(value, ".12g")
	return value


def _requirement_manifest_hash(content: bytes) -> str:
	with zipfile.ZipFile(io.BytesIO(content)) as archive:
		manifest_names = [name for name in archive.namelist() if name.endswith("/00-manifiesto.json")]
		if len(manifest_names) != 1:
			raise ValueError("El ZIP no contiene un manifiesto único.")
		manifest = json.loads(archive.read(manifest_names[0]))
		return str(manifest.get("manifest_sha256") or "")


class _CountingRows:
	def __init__(self, rows: Iterable[Mapping[str, Any]]):
		self.rows = iter(rows)
		self.count = 0

	def __iter__(self):
		for row in self.rows:
			self.count += 1
			yield row
