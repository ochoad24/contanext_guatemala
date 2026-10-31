from __future__ import annotations

import hashlib
import json
from typing import Any

import frappe


MAX_XML_BYTES = 5 * 1024 * 1024
MAX_PDF_BYTES = 20 * 1024 * 1024


def canonical_json(value: Any) -> bytes:
	return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(content: bytes) -> str:
	return hashlib.sha256(content).hexdigest()


def snapshot_hash(snapshot: dict[str, Any]) -> str:
	return sha256_hex(canonical_json(snapshot))


def save_private_artifact(*, operation_name: str, filename: str, content: bytes, artifact_type: str):
	artifact = artifact_type.upper()
	if artifact not in {"REQUEST_XML", "CERTIFIED_XML", "PDF"}:
		raise ValueError("Tipo de artefacto FEL no soportado.")
	limit = MAX_PDF_BYTES if artifact == "PDF" else MAX_XML_BYTES
	if not content or len(content) > limit:
		raise ValueError("El artefacto FEL está vacío o excede el tamaño permitido.")
	if artifact == "PDF" and not content.startswith(b"%PDF-"):
		raise ValueError("La representación gráfica no contiene una firma PDF válida.")

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": filename,
			"is_private": 1,
			"attached_to_doctype": "FEL Operation",
			"attached_to_name": operation_name,
			"content": content,
		}
	).insert(ignore_permissions=True)
	return file_doc, sha256_hex(content)


def record_fel_event(operation_name: str, event_type: str, details: dict[str, Any] | None = None) -> str:
	operation = frappe.db.get_value("FEL Operation", operation_name, ["company", "status"], as_dict=True)
	if not operation:
		raise frappe.DoesNotExistError(operation_name)
	event = frappe.get_doc(
		{
			"doctype": "GT FEL Operation Event",
			"fel_operation": operation_name,
			"company": operation.company,
			"event_type": event_type,
			"status": operation.status,
			"actor": frappe.session.user,
			"details": json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
		}
	).insert(ignore_permissions=True)
	return event.name
