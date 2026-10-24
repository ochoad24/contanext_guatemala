import math
from dataclasses import dataclass
from enum import StrEnum

from contanext_guatemala.books.snapshots import canonical_json, sha256_hex


class PrintMode(StrEnum):
	SIMPLEX = "SIMPLEX"
	DUPLEX = "DUPLEX"


class FolioStatus(StrEnum):
	RESERVED = "Reserved"
	CONSUMED = "Consumed"
	ANNULLED = "Annulled"
	RELEASED = "Released"


@dataclass(frozen=True, slots=True)
class FolioRange:
	first: int
	last: int
	count: int
	page_count: int
	print_mode: PrintMode


def required_folios(page_count: int, print_mode: PrintMode | str, *, duplex_enabled: bool = False) -> int:
	if page_count < 1:
		raise ValueError("El PDF debe contener al menos una página.")
	mode = PrintMode(print_mode)
	if mode == PrintMode.DUPLEX and not duplex_enabled:
		raise ValueError("DUPLEX permanece bloqueado hasta cerrar G1 y G4.")
	return page_count if mode == PrintMode.SIMPLEX else math.ceil(page_count / 2)


def plan_range(
	first: int,
	page_count: int,
	print_mode: PrintMode | str = PrintMode.SIMPLEX,
	*,
	duplex_enabled: bool = False,
) -> FolioRange:
	if first < 1:
		raise ValueError("El primer folio debe ser positivo.")
	mode = PrintMode(print_mode)
	count = required_folios(page_count, mode, duplex_enabled=duplex_enabled)
	return FolioRange(first, first + count - 1, count, page_count, mode)


def validate_failed_pages(page_count: int, failed_pages: list[int]) -> tuple[int, ...]:
	normalized = tuple(sorted(set(failed_pages)))
	if any(page < 1 or page > page_count for page in normalized):
		raise ValueError("Una página fallida queda fuera del PDF reservado.")
	return normalized


def reserve_technical_folios(
	book_run: str, page_count: int, idempotency_key: str, *, actor: str | None = None
):
	"""Reserve a non-legal range while holding the company's settings row lock."""
	import frappe
	from frappe.utils import now_datetime

	existing = frappe.db.get_value(
		"GT Book Folio Allocation", {"idempotency_key": idempotency_key}, "name"
	)
	if existing:
		allocation = frappe.get_doc("GT Book Folio Allocation", existing)
		if allocation.book_run != book_run or allocation.page_count != page_count:
			frappe.throw("La clave de idempotencia ya fue usada con otro alcance.")
		return allocation
	doc = frappe.get_doc("GT Accounting Book Run", book_run)
	settings_lock = frappe.db.sql(
		"SELECT name FROM `tabGT Accounting Book Settings` WHERE company=%s FOR UPDATE",
		(doc.company,),
	)
	if not settings_lock:
		frappe.throw("La empresa no tiene una configuración de libros que pueda bloquearse.")
	last = frappe.db.sql(
		"""SELECT COALESCE(MAX(last_folio), 0)
		FROM `tabGT Book Folio Allocation`
		WHERE company=%s AND book_type=%s AND technical_simulation=1""",
		(doc.company, doc.book_type),
	)[0][0]
	planned = plan_range(int(last) + 1, page_count)
	actor = actor or frappe.session.user
	allocation = frappe.get_doc(
		{
			"doctype": "GT Book Folio Allocation",
			"book_run": doc.name,
			"company": doc.company,
			"book_type": doc.book_type,
			"idempotency_key": idempotency_key,
			"technical_simulation": 1,
			"print_mode": planned.print_mode.value,
			"page_count": planned.page_count,
			"folio_count": planned.count,
			"first_folio": planned.first,
			"last_folio": planned.last,
			"status": FolioStatus.RESERVED.value,
			"reserved_by": actor,
			"reserved_at": now_datetime(),
		}
	).insert(ignore_permissions=True)
	record_folio_event(allocation, "RESERVED", f"{idempotency_key}:reserved", actor=actor)
	return allocation


def record_folio_event(
	allocation,
	action: str,
	idempotency_key: str,
	*,
	failed_pages: tuple[int, ...] = (),
	reason: str | None = None,
	actor: str | None = None,
):
	import frappe
	from frappe.utils import now_datetime

	existing = frappe.db.get_value("GT Book Folio Event", {"idempotency_key": idempotency_key}, "name")
	if existing:
		return frappe.get_doc("GT Book Folio Event", existing)
	frappe.db.sql(
		"SELECT name FROM `tabGT Book Folio Allocation` WHERE name=%s FOR UPDATE", (allocation.name,)
	)
	previous = frappe.db.get_value(
		"GT Book Folio Event",
		{"allocation": allocation.name},
		"event_sha256",
		order_by="event_at desc, creation desc",
	) or ""
	event_at = now_datetime()
	actor = actor or frappe.session.user
	payload = {
		"allocation": allocation.name,
		"book_run": allocation.book_run,
		"action": action,
		"actor": actor,
		"event_at": str(event_at),
		"idempotency_key": idempotency_key,
		"failed_pages": list(failed_pages),
		"reason": reason,
		"previous_event_sha256": previous,
	}
	return frappe.get_doc(
		{
			"doctype": "GT Book Folio Event",
			"allocation": allocation.name,
			"book_run": allocation.book_run,
			"company": allocation.company,
			"action": action,
			"actor": actor,
			"event_at": event_at,
			"idempotency_key": idempotency_key,
			"failed_pages_json": canonical_json(list(failed_pages)).decode(),
			"reason": reason,
			"previous_event_sha256": previous,
			"event_sha256": sha256_hex(canonical_json(payload)),
		}
	).insert(ignore_permissions=True)
