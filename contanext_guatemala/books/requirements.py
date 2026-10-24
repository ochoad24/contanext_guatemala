import csv
import io
import json
import re
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from contanext_guatemala.books.exports import _export_value
from contanext_guatemala.books.pdf_validation import validate_pdf
from contanext_guatemala.books.snapshots import canonical_json, sha256_hex


PACKAGE_SCHEMA = "contanext.gt.accounting-book.requirement-package"
PACKAGE_VERSION = 1
ALLOWED_ARTIFACT_TYPES = {"CSV", "SEALED_PDF", "SEAL_MANIFEST"}
_FIXED_ZIP_TIME = (2020, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class PackageEntry:
	path: str
	content: bytes


def missing_requested_artifacts(wanted: Iterable[str], available: Iterable[str]) -> set[str]:
	return set(wanted) - set(available)


def safe_component(value: str, fallback: str = "sin-referencia") -> str:
	value = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip()).strip(".-")
	return value[:100] or fallback


def validate_entry_path(path: str) -> str:
	normalized = str(PurePosixPath(path))
	if not normalized or normalized.startswith("/") or ".." in PurePosixPath(normalized).parts:
		raise ValueError("La ruta del paquete no es segura.")
	return normalized


def support_index_csv(rows: Iterable[Mapping[str, Any]]) -> bytes:
	output = io.StringIO(newline="")
	writer = csv.writer(output, lineterminator="\n")
	writer.writerow(("tipo_documento", "referencia", "fecha", "descripcion", "sha256", "archivo_incluido"))
	for row in rows:
		writer.writerow(
			(
				_export_value(row.get("document_type") or ""),
				_export_value(row.get("reference") or ""),
				_export_value(row.get("document_date") or ""),
				_export_value(row.get("description") or ""),
				_export_value(row.get("sha256") or ""),
				"NO",
			)
		)
	return ("\ufeff" + output.getvalue()).encode("utf-8")


def build_requirement_manifest(*, package: Mapping[str, Any], entries: Iterable[PackageEntry]) -> dict:
	files = [
		{"path": validate_entry_path(entry.path), "size": len(entry.content), "sha256": sha256_hex(entry.content)}
		for entry in sorted(entries, key=lambda item: item.path)
	]
	payload = {
		"schema": PACKAGE_SCHEMA,
		"version": PACKAGE_VERSION,
		"package": dict(package),
		"files": files,
		"notice": "PAQUETE CONTROLADO — verificar alcance, destinatario y hashes antes de entregar",
	}
	payload["manifest_sha256"] = sha256_hex(canonical_json(payload))
	return payload


def build_requirement_zip(root: str, entries: Iterable[PackageEntry], manifest: Mapping[str, Any]) -> bytes:
	root = safe_component(root)
	items = list(entries) + [PackageEntry("00-manifiesto.json", canonical_json(manifest))]
	seen: set[str] = set()
	output = io.BytesIO()
	with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
		for item in sorted(items, key=lambda value: value.path):
			path = validate_entry_path(f"{root}/{item.path}")
			if path in seen:
				raise ValueError(f"Ruta duplicada en el paquete: {path}")
			seen.add(path)
			info = zipfile.ZipInfo(path, date_time=_FIXED_ZIP_TIME)
			info.compress_type = zipfile.ZIP_DEFLATED
			info.external_attr = 0o600 << 16
			archive.writestr(info, item.content)
	return output.getvalue()


def verify_requirement_zip(content: bytes) -> bool:
	"""Verify a requirement ZIP without trusting its filename or database record."""
	try:
		with zipfile.ZipFile(io.BytesIO(content)) as archive:
			infos = archive.infolist()
			names = [info.filename for info in infos]
			if len(names) != len(set(names)) or any(info.is_dir() for info in infos):
				return False
			if any(validate_entry_path(name) != name for name in names):
				return False
			roots = {PurePosixPath(name).parts[0] for name in names}
			if len(roots) != 1:
				return False
			root = next(iter(roots))
			manifest_name = f"{root}/00-manifiesto.json"
			if names.count(manifest_name) != 1:
				return False
			manifest = json.loads(archive.read(manifest_name))
			if not isinstance(manifest, dict):
				return False
			if manifest.get("schema") != PACKAGE_SCHEMA or manifest.get("version") != PACKAGE_VERSION:
				return False
			expected_hash = manifest.get("manifest_sha256")
			unsigned = dict(manifest)
			unsigned.pop("manifest_sha256", None)
			if not expected_hash or sha256_hex(canonical_json(unsigned)) != expected_hash:
				return False
			expected_files = manifest.get("files")
			if not isinstance(expected_files, list):
				return False
			expected_paths = {item.get("path") for item in expected_files if isinstance(item, dict)}
			actual_paths = {name.removeprefix(f"{root}/") for name in names if name != manifest_name}
			if len(expected_paths) != len(expected_files) or expected_paths != actual_paths:
				return False
			for item in expected_files:
				path = validate_entry_path(item["path"])
				payload = archive.read(f"{root}/{path}")
				if len(payload) != item.get("size") or sha256_hex(payload) != item.get("sha256"):
					return False
			return True
	except (ValueError, KeyError, TypeError, RuntimeError, json.JSONDecodeError, zipfile.BadZipFile):
		return False


def generate_requirement_package(package_name: str) -> dict:
	import frappe
	from frappe.utils.file_manager import save_file

	doc = frappe.get_doc("GT Requirement Package", package_name)
	doc.check_permission("write")
	if "GT Books Manager" not in frappe.get_roles():
		frappe.throw("La generación de paquetes requiere el rol GT Books Manager.")
	if doc.status == "Generated":
		return {"status": doc.status, "sha256": doc.package_sha256}
	if doc.status != "Draft":
		frappe.throw("El paquete no está disponible para generación.")
	_validate_package_scope(doc)
	entries = _collect_entries(doc)
	index = support_index_csv(row.as_dict() for row in doc.support_index)
	entries.append(PackageEntry("09-indice-soportes.csv", index))
	manifest = build_requirement_manifest(
		package={
			"name": doc.name,
			"reference": doc.request_reference,
			"company": doc.company,
			"period_from": doc.period_from,
			"period_to": doc.period_to,
			"purpose": doc.purpose,
			"recipient": doc.recipient,
			"book_runs": sorted(row.book_run for row in doc.book_runs),
		},
		entries=entries,
	)
	content = build_requirement_zip(doc.request_reference, entries, manifest)
	file_doc = save_file(
		f"requerimiento-{safe_component(doc.request_reference)}.zip",
		content,
		doc.doctype,
		doc.name,
		is_private=True,
	)
	doc.package_file = file_doc.file_url
	doc.package_sha256 = sha256_hex(content)
	doc.manifest_sha256 = manifest["manifest_sha256"]
	doc.generated_by = frappe.session.user
	doc.generated_at = frappe.utils.now_datetime()
	doc.status = "Generated"
	doc.flags.controlled_transition = True
	doc.save(ignore_permissions=True)
	record_package_event(doc, "GENERATED", f"ZIP SHA-256: {doc.package_sha256}")
	return {"status": doc.status, "sha256": doc.package_sha256, "file_count": len(entries)}


def _validate_package_scope(doc) -> None:
	import frappe
	from frappe.utils import getdate

	if not doc.book_runs:
		frappe.throw("Seleccione al menos una emisión.")
	seen = set()
	for selection in doc.book_runs:
		if selection.book_run in seen:
			frappe.throw("Una emisión no puede seleccionarse dos veces.")
		seen.add(selection.book_run)
		run = frappe.db.get_value(
			"GT Accounting Book Run",
			selection.book_run,
			["company", "period_from", "period_to", "status"],
			as_dict=True,
		)
		if not run or run.company != doc.company or run.status not in {"Sealed", "Superseded"}:
			frappe.throw("Cada emisión debe estar sellada y pertenecer a la empresa del paquete.")
		if getdate(run.period_from) < getdate(doc.period_from) or getdate(run.period_to) > getdate(doc.period_to):
			frappe.throw("Cada emisión debe estar contenida en el período solicitado.")


def _collect_entries(doc) -> list[PackageEntry]:
	import frappe

	entries: list[PackageEntry] = []
	book_folders = {
		"JOURNAL": "02-libro-diario", "LEDGER": "03-libro-mayor",
		"INVENTORY": "04-libro-inventarios", "FINANCIAL_STATEMENTS": "05-estados-financieros",
		"TRIAL_BALANCE": "06-balance-comprobacion",
	}
	for selection in sorted(doc.book_runs, key=lambda row: row.book_run):
		run = frappe.get_doc("GT Accounting Book Run", selection.book_run)
		folder = book_folders[run.book_type]
		wanted = set()
		if selection.include_pdf:
			wanted.add("SEALED_PDF")
		if selection.include_csv:
			wanted.add("CSV")
		if selection.include_manifest:
			wanted.add("SEAL_MANIFEST")
		found = set()
		for artifact in run.artifacts:
			if artifact.artifact_type not in wanted or artifact.artifact_type not in ALLOWED_ARTIFACT_TYPES:
				continue
			found.add(artifact.artifact_type)
			content = _private_file_content(artifact.file_url, artifact.sha256)
			extension = {"SEALED_PDF": "pdf", "CSV": "csv", "SEAL_MANIFEST": "json"}[artifact.artifact_type]
			entries.append(
				PackageEntry(
					f"{folder}/{safe_component(run.name)}-{artifact.artifact_type.lower()}.{extension}",
					content,
				)
			)
		missing = missing_requested_artifacts(wanted, found)
		if missing:
			frappe.throw(
				f"La emisión {run.name} no contiene los artefactos solicitados: {', '.join(sorted(missing))}."
			)
		if selection.include_authorizations:
			for authorization in run.authorizations:
				evidence = frappe.get_doc("GT Book Authorization Evidence", authorization.authorization_evidence)
				if evidence.company != doc.company:
					frappe.throw("La evidencia seleccionada pertenece a otra empresa.")
				if evidence.status != "Verified":
					frappe.throw("Solo se pueden incluir evidencias verificadas.")
				content = _private_file_content(evidence.resolution_file)
				validate_pdf(content)
				entries.append(
					PackageEntry(
						f"01-autorizaciones/{safe_component(evidence.authority)}-"
						f"{safe_component(evidence.resolution_number)}-{safe_component(evidence.name)}.pdf",
						content,
					)
				)
	return entries


def _private_file_content(file_url: str, expected_sha256: str | None = None) -> bytes:
	import frappe

	file_doc = frappe.get_doc("File", {"file_url": file_url})
	if not file_doc.is_private:
		frappe.throw("El paquete no puede incluir archivos públicos.")
	content = file_doc.get_content()
	content = content.encode() if isinstance(content, str) else content
	if expected_sha256 and sha256_hex(content) != expected_sha256:
		frappe.throw("Un artefacto no coincide con el hash de la emisión.")
	return content


def record_package_event(doc, action: str, detail: str | None = None) -> None:
	import frappe

	frappe.get_doc({
		"doctype": "GT Requirement Package Event", "requirement_package": doc.name,
		"company": doc.company, "action": action, "actor": frappe.session.user,
		"event_at": frappe.utils.now_datetime(), "purpose": doc.purpose,
		"recipient": doc.recipient, "detail": detail,
	}).insert(ignore_permissions=True)


def audit_package_download(package_name: str) -> None:
	import frappe

	doc = frappe.get_doc("GT Requirement Package", package_name)
	doc.check_permission("read")
	if doc.status != "Released":
		frappe.throw("El paquete no ha sido liberado para descarga.")
	record_package_event(doc, "DOWNLOADED")
	content = _private_file_content(doc.package_file, doc.package_sha256)
	frappe.local.response.filename = f"requerimiento-{safe_component(doc.request_reference)}.zip"
	frappe.local.response.filecontent = content
	frappe.local.response.type = "download"
