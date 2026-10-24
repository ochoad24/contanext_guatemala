import gzip
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from contanext_guatemala.books.audit import record_book_event
from contanext_guatemala.books.folios import reserve_technical_folios
from contanext_guatemala.books.manifests import build_seal_manifest
from contanext_guatemala.books.pdf_poc import chromium_executable, render_html
from contanext_guatemala.books.rendering import (
	assert_stable_pagination,
	build_prototype_html,
	replace_folio_markers,
)
from contanext_guatemala.books.snapshots import canonical_json, sha256_hex


BOOK_TITLES = {
	"JOURNAL": "Libro Diario",
	"LEDGER": "Libro Mayor",
	"TRIAL_BALANCE": "Balance de comprobación",
	"FINANCIAL_STATEMENTS": "Libro de Estados Financieros",
	"INVENTORY": "Libro de Inventarios",
}


def seal_book_run(book_run: str, sealing_key: str, requested_by: str) -> dict:
	import frappe

	lock = frappe.cache.lock(f"gt-book-sealing:{book_run}", timeout=21_600)
	if not lock.acquire(blocking=False):
		return {"status": "Sealing", "reason": "already_running"}
	try:
		return _seal_book_run(book_run, sealing_key, requested_by)
	finally:
		if lock.owned():
			lock.release()


def _seal_book_run(book_run: str, sealing_key: str, requested_by: str) -> dict:
	import frappe
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("GT Accounting Book Run", book_run)
	if doc.status == "Awaiting Print Confirmation" and doc.sealing_key == sealing_key:
		return {"status": doc.status, "pdf_sha256": doc.pdf_sha256}
	if doc.status != "Sealing" or doc.sealing_key != sealing_key:
		frappe.throw("La clave o el estado de sellado ya no están vigentes.")
	allocation = None
	try:
		_block_if_volatile_preflight_fails(doc)
		if doc.annexes:
			frappe.throw(
				"La composición foliada de anexos permanece bloqueada hasta aprobar el formato G2."
			)
		manifest = json.loads(doc.snapshot_manifest)
		rows = list(_snapshot_rows(doc))
		identity = json.loads(doc.tax_identity_snapshot or "{}")
		accountant = json.loads(doc.accountant_snapshot or "{}")
		representative = json.loads(doc.representative_snapshot or "{}")
		authorizations = _authorization_labels(doc)
		html, expected_pages = build_prototype_html(
			book_title=BOOK_TITLES[doc.book_type],
			company=doc.company,
			period=f"{doc.period_from} a {doc.period_to}",
			tax_identity=identity,
			columns=manifest["metadata"]["columns"],
			rows=rows,
			emission_sha256=doc.emission_sha256,
			authorizations=authorizations,
			signatories={"accountant": accountant.get("name"), "representative": representative.get("name")},
		)
		private_root = frappe.get_site_path("private")
		with TemporaryDirectory(prefix="gt-book-seal-", dir=private_root) as temporary:
			root = Path(temporary)
			pre_html = root / "preliminary.html"
			pre_pdf = root / "preliminary.pdf"
			pre_html.write_text(html, encoding="utf-8")
			preliminary = render_html(pre_html, pre_pdf)
			if preliminary.page_count != expected_pages:
				frappe.throw("Chromium no respetó la paginación explícita del formato fijado.")
			allocation = reserve_technical_folios(
				doc.name, preliminary.page_count, sealing_key, actor=requested_by
			)
			final_html = root / "final.html"
			final_pdf = root / "final.pdf"
			final_html.write_text(
				replace_folio_markers(html, allocation.first_folio, allocation.page_count),
				encoding="utf-8",
			)
			final = render_html(final_html, final_pdf)
			assert_stable_pagination(preliminary, final)
			pdf_content = final_pdf.read_bytes()
		pdf_sha256 = sha256_hex(pdf_content)
		allocation.db_set("pdf_sha256", pdf_sha256, update_modified=False)
		pdf_file = save_file(
			f"{doc.name}-impresion-tecnica.pdf", pdf_content, doc.doctype, doc.name, is_private=True
		)
		artifact_payload = [
			{"type": row.artifact_type, "file_url": row.file_url, "sha256": row.sha256}
			for row in doc.artifacts
		] + [{"type": "SEALED_PDF", "file_url": pdf_file.file_url, "sha256": pdf_sha256}]
		seal_manifest = build_seal_manifest(
			book_run=doc.name,
			emission_sha256=doc.emission_sha256,
			pdf_sha256=pdf_sha256,
			page_count=final.page_count,
			allocation={
				"name": allocation.name,
				"technical_simulation": True,
				"print_mode": allocation.print_mode,
				"first_folio": allocation.first_folio,
				"last_folio": allocation.last_folio,
				"folio_count": allocation.folio_count,
			},
			artifacts=artifact_payload,
			renderer={
				"engine": "Chromium",
				"version": _chromium_version(),
				"format": "PROTOTYPE-1",
				"font": "DejaVu Sans",
			},
		)
		manifest_content = canonical_json(seal_manifest)
		manifest_file = save_file(
			f"{doc.name}-manifiesto-sellado.json",
			manifest_content,
			doc.doctype,
			doc.name,
			is_private=True,
		)
		doc.append("artifacts", {
			"artifact_type": "SEALED_PDF", "file_url": pdf_file.file_url,
			"content_type": "application/pdf", "row_count": final.page_count, "sha256": pdf_sha256,
		})
		doc.append("artifacts", {
			"artifact_type": "SEAL_MANIFEST", "file_url": manifest_file.file_url,
			"content_type": "application/json", "row_count": 0, "sha256": sha256_hex(manifest_content),
		})
		doc.folio_allocation = allocation.name
		doc.print_mode = allocation.print_mode
		doc.pdf_page_count = final.page_count
		doc.pdf_sha256 = pdf_sha256
		doc.seal_manifest_sha256 = seal_manifest["manifest_sha256"]
		doc.sealed_pdf = pdf_file.file_url
		doc.seal_manifest_file = manifest_file.file_url
		doc.flags.in_sealing = True
		doc.save(ignore_permissions=True)
		doc.db_set("status", "Awaiting Print Confirmation")
		doc.reload()
		record_book_event(doc, "PDF_CREATED")
		record_book_event(doc, "AWAITING_PRINT_CONFIRMATION")
		return {"status": doc.status, "pdf_sha256": pdf_sha256, "page_count": final.page_count}
	except Exception:
		if frappe.db.get_value("GT Accounting Book Run", doc.name, "status") == "Sealing":
			doc.db_set("status", "Seal Failed")
		frappe.log_error(title=f"Sellado técnico de libro GT: {book_run}", message=frappe.get_traceback())
		raise


def _snapshot_rows(doc):
	import frappe

	parts = sorted(
		(row for row in doc.artifacts if row.artifact_type == "SNAPSHOT_PART"),
		key=lambda row: row.part_index,
	)
	for artifact in parts:
		file_doc = frappe.get_doc("File", {"file_url": artifact.file_url})
		content = file_doc.get_content()
		if isinstance(content, str):
			content = content.encode()
		if sha256_hex(content) != artifact.sha256:
			frappe.throw("Un archivo de snapshot no coincide con su hash aprobado.")
		for line in gzip.decompress(content).splitlines():
			if line:
				yield json.loads(line)


def _authorization_labels(doc) -> list[str]:
	import frappe

	labels = []
	for row in doc.authorizations:
		value = frappe.db.get_value(
			"GT Book Authorization Evidence", row.authorization_evidence,
			["authority", "resolution_number"], as_dict=True,
		)
		if value:
			labels.append(f"{value.authority}: {value.resolution_number}")
	return labels


def _block_if_volatile_preflight_fails(doc) -> None:
	from contanext_guatemala.books.preflight import CHECKS

	results = [result for check in CHECKS for result in check(doc)]
	if any(result.blocks for result in results):
		raise RuntimeError("El preflight volátil detectó una condición bloqueante.")


def _chromium_version() -> str:
	result = subprocess.run(
		[chromium_executable(), "--version"], check=False, capture_output=True, text=True, timeout=10
	)
	return result.stdout.strip() or "unknown"
