from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import frappe


@dataclass(frozen=True, slots=True)
class PostCommitDispatch:
	key: str
	mode: str


def schedule_after_commit(
	*,
	key: str,
	immediate: Callable[..., None],
	fallback_job: str,
	kwargs: dict[str, Any] | None = None,
	queue: str = "short",
) -> PostCommitDispatch:
	"""Run once after commit and enqueue a safe fallback if local execution fails.

	The key only deduplicates registrations in the current request. Durable
	idempotency belongs to FEL Operation and is deliberately not simulated here.
	"""
	normalized_key = key.strip()
	if not normalized_key:
		raise ValueError("La clave post-commit es obligatoria.")
	if not fallback_job.strip():
		raise ValueError("El trabajo de respaldo es obligatorio.")

	registered = getattr(frappe.local, "contanext_fel_after_commit", None)
	if registered is None:
		registered = set()
		frappe.local.contanext_fel_after_commit = registered
	if normalized_key in registered:
		return PostCommitDispatch(key=normalized_key, mode="ALREADY_REGISTERED")
	registered.add(normalized_key)

	payload = dict(kwargs or {})

	def dispatch() -> None:
		try:
			immediate(**payload)
		except Exception:
			frappe.log_error(
				title="FEL post-commit fallback",
				message=f"Falló el intento post-commit para {normalized_key}; se trasladó a cola.",
			)
			frappe.enqueue(
				fallback_job,
				queue=queue,
				job_id=f"fel-post-commit::{normalized_key}",
				**payload,
			)

	frappe.db.after_commit.add(dispatch)
	return PostCommitDispatch(key=normalized_key, mode="AFTER_COMMIT")
