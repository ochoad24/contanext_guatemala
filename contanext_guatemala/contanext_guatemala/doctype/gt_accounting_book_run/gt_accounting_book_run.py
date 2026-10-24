import json

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

from contanext_guatemala.books.constants import UNAUTHORIZED_DRAFT_LABEL
from contanext_guatemala.books.workflow import TransitionContext, validate_transition


SEALED_STATUSES = {"Sealed", "Superseded"}
GENERATED_STATUSES = {
	"Generated",
	"Ready for Review",
	"Approved",
	"Rejected",
	"Sealing",
	"Awaiting Print Confirmation",
	"Print Exception",
	"Sealed",
	"Seal Failed",
	"Superseded",
}
GENERATED_PROTECTED = {
	"generation_key",
	"generation_progress",
	"generation_message",
	"generated_at",
	"row_count",
	"emission_sha256",
	"reconciliation_json",
	"snapshot_manifest",
}
SEAL_PROTECTED = {
	"sealing_key",
	"folio_allocation",
	"print_mode",
	"pdf_page_count",
	"pdf_sha256",
	"seal_manifest_sha256",
	"sealed_pdf",
	"seal_manifest_file",
}
PROTECTED_AFTER_PREFLIGHT = {
	"company",
	"book_type",
	"period_from",
	"period_to",
	"fiscal_year",
	"finance_book",
	"currency",
	"physical_count_import",
	"tax_identity_snapshot",
	"accountant_snapshot",
	"representative_snapshot",
	"supersedes",
	"correction_reason",
	"annexes",
}


class GTAccountingBookRun(Document):
	def before_insert(self) -> None:
		self.prepared_by = frappe.session.user
		self.generation_mode = "Technical Draft"
		self.draft_notice = UNAUTHORIZED_DRAFT_LABEL
		self.status = "Draft"
		self.preflight_status = "Not Run"
		self.generation_number = 1
		self._take_identity_snapshot()

	def validate(self) -> None:
		self.generation_mode = "Technical Draft"
		self.draft_notice = UNAUTHORIZED_DRAFT_LABEL
		if not self.is_new():
			self.prepared_by = self.owner
		if self.currency != "GTQ":
			frappe.throw("La moneda de una emisión guatemalteca debe ser GTQ.")
		if self.period_from and self.period_to and getdate(self.period_from) > getdate(self.period_to):
			frappe.throw("La fecha inicial no puede ser posterior a la fecha final.")
		if self.supersedes and not self.correction_reason:
			frappe.throw("Una sustitución requiere motivo de corrección.")
		self._validate_settings_company()
		self._validate_supersession()
		self._validate_authorizations()
		self._validate_annexes()
		self._validate_physical_count()
		self._prevent_protected_mutation()

	def on_trash(self) -> None:
		if self.status in SEALED_STATUSES:
			frappe.throw("Una emisión sellada o sustituida no se puede eliminar.")

	def _validate_settings_company(self) -> None:
		settings = frappe.db.get_value(
			"GT Accounting Book Settings",
			{"company": self.company},
			["name", "enabled"],
			as_dict=True,
		)
		if not settings or not settings.enabled:
			frappe.throw("La empresa no tiene habilitados los borradores técnicos de libros.")

	def _validate_authorizations(self) -> None:
		seen: set[str] = set()
		for row in self.authorizations:
			if row.authorization_evidence in seen:
				frappe.throw("No se puede vincular dos veces la misma evidencia.")
			seen.add(row.authorization_evidence)
			evidence = frappe.db.get_value(
				"GT Book Authorization Evidence",
				row.authorization_evidence,
				["company", "book_type"],
				as_dict=True,
			)
			if not evidence or evidence.company != self.company or evidence.book_type != self.book_type:
				frappe.throw("Cada evidencia debe pertenecer a la empresa y tipo de libro de la emisión.")

	def _validate_supersession(self) -> None:
		if not self.supersedes:
			return
		if self.name and self.supersedes == self.name:
			frappe.throw("Una emisión no puede sustituirse a sí misma.")
		previous = frappe.db.get_value(
			"GT Accounting Book Run",
			self.supersedes,
			[
				"company",
				"book_type",
				"period_from",
				"period_to",
				"fiscal_year",
				"finance_book",
				"currency",
				"status",
			],
			as_dict=True,
		)
		if not previous or previous.status != "Sealed":
			frappe.throw("La emisión sustituida debe existir y conservar el estado técnico Sealed.")
		fields = ("company", "book_type", "fiscal_year", "finance_book", "currency")
		different_scope = any(
			(previous.get(field) or None) != (self.get(field) or None) for field in fields
		)
		different_period = any(
			getdate(previous.get(field)) != getdate(self.get(field))
			for field in ("period_from", "period_to")
		)
		if different_scope or different_period:
			frappe.throw("Una sustitución debe conservar empresa, libro, período, ejercicio, libro financiero y moneda.")

	def _validate_annexes(self) -> None:
		if self.book_type != "FINANCIAL_STATEMENTS" and self.annexes:
			frappe.throw("Los anexos de estados financieros solo se permiten en ese tipo de libro.")
		seen: set[str] = set()
		for row in self.annexes:
			if row.annex in seen:
				frappe.throw("No se puede vincular dos veces el mismo anexo.")
			seen.add(row.annex)
			annex = frappe.db.get_value(
				"GT Financial Statement Annex",
				row.annex,
				["company", "title", "annex_type", "period_from", "period_to", "version", "display_order", "status", "pdf_file", "sha256", "approved_by", "approved_at"],
				as_dict=True,
			)
			if not annex or annex.company != self.company or annex.status != "Approved":
				frappe.throw("Cada anexo debe estar aprobado y pertenecer a la empresa de la emisión.")
			if getdate(annex.period_from) != getdate(self.period_from) or getdate(annex.period_to) != getdate(self.period_to):
				frappe.throw("El período de cada anexo debe coincidir exactamente con la emisión.")
			row.display_order = row.display_order or annex.display_order
			row.title_snapshot = annex.title
			row.annex_type_snapshot = annex.annex_type
			row.version_snapshot = annex.version
			row.file_url_snapshot = annex.pdf_file
			row.sha256_snapshot = annex.sha256
			row.approved_by_snapshot = annex.approved_by
			row.approved_at_snapshot = annex.approved_at

	def _validate_physical_count(self) -> None:
		if self.book_type != "INVENTORY" and self.physical_count_import:
			frappe.throw("El conteo físico solo se permite en el Libro de Inventarios.")
		if self.book_type != "INVENTORY" or not self.physical_count_import:
			return
		physical_count = frappe.db.get_value(
			"GT Physical Count Import",
			self.physical_count_import,
			["company", "cutoff_date", "status"],
			as_dict=True,
		)
		if (
			not physical_count
			or physical_count.company != self.company
			or physical_count.status != "Approved"
			or getdate(physical_count.cutoff_date) != getdate(self.period_to)
		):
			frappe.throw("El conteo físico debe estar aprobado, pertenecer a la empresa y coincidir con el corte.")

	def _prevent_protected_mutation(self) -> None:
		if self.is_new():
			return
		old = self.get_doc_before_save()
		if old and old.status in SEALED_STATUSES:
			frappe.throw("Una emisión sellada o sustituida es inmutable.")
		if old and old.status != self.status:
			frappe.throw("El estado solo puede cambiar mediante una transición controlada.")
		if old and old.preflight_status != "Not Run":
			changed = [field for field in PROTECTED_AFTER_PREFLIGHT if field != "annexes" and self.get(field) != old.get(field)]
			old_evidence = [row.authorization_evidence for row in old.authorizations]
			new_evidence = [row.authorization_evidence for row in self.authorizations]
			if old_evidence != new_evidence:
				changed.append("authorizations")
			old_annexes = [(row.annex, row.display_order, row.sha256_snapshot) for row in old.annexes]
			new_annexes = [(row.annex, row.display_order, row.sha256_snapshot) for row in self.annexes]
			if old_annexes != new_annexes:
				changed.append("annexes")
			if changed:
				frappe.throw("El alcance no puede cambiar después del preflight: " + ", ".join(sorted(changed)))
		if old and old.status in GENERATED_STATUSES:
			changed = [field for field in GENERATED_PROTECTED if self.get(field) != old.get(field)]
			old_artifacts = [
				(row.artifact_type, row.part_index, row.file_url, row.sha256) for row in old.artifacts
			]
			new_artifacts = [
				(row.artifact_type, row.part_index, row.file_url, row.sha256) for row in self.artifacts
			]
			if old_artifacts != new_artifacts and not self.flags.get("in_sealing"):
				changed.append("artifacts")
			if changed:
				frappe.throw("Los artefactos generados son inmutables: " + ", ".join(sorted(changed)))
		if old and old.status in {"Awaiting Print Confirmation", "Print Exception", "Sealed", "Superseded"}:
			changed = [field for field in SEAL_PROTECTED if self.get(field) != old.get(field)]
			if changed:
				frappe.throw("El PDF, manifiesto y rango reservado son inmutables: " + ", ".join(sorted(changed)))

	def _take_identity_snapshot(self) -> None:
		profile_name = frappe.db.get_value("GT Accounting Book Settings", {"company": self.company}, "tax_profile")
		if not profile_name:
			return
		profile = frappe.get_doc("ContaNext Tax Profile", profile_name)
		self.tax_identity_snapshot = _json(
			{
				"tax_profile": profile.name,
				"nit": profile.nit,
				"fiscal_name_for_books": profile.fiscal_name_for_books,
				"tax_address": profile.tax_address,
				"fiscal_establishment": profile.fiscal_establishment,
				"accounting_framework": profile.accounting_framework,
			}
		)
		self.accountant_snapshot = _json(
			{
				"name": profile.accountant_name,
				"nit": profile.accountant_nit,
				"registration": profile.accountant_registration,
			}
		)
		self.representative_snapshot = _json(
			{
				"name": profile.legal_representative_name,
				"identification": profile.get_password("legal_representative_id", raise_exception=False),
			}
		)


def _json(value: dict) -> str:
	return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


@frappe.whitelist()
def run_preflight(book_run: str) -> dict:
	doc = frappe.get_doc("GT Accounting Book Run", book_run)
	doc.check_permission("write")
	if doc.status != "Draft":
		frappe.throw("El preflight de Fase 1 solo puede ejecutarse sobre un borrador.")
	from contanext_guatemala.books.preflight import execute_preflight

	return execute_preflight(doc)


@frappe.whitelist()
def request_generation(book_run: str) -> dict:
	doc = frappe.get_doc("GT Accounting Book Run", book_run)
	doc.check_permission("write")
	if doc.book_type not in {"JOURNAL", "LEDGER", "TRIAL_BALANCE", "FINANCIAL_STATEMENTS", "INVENTORY"}:
		frappe.throw("Este tipo de libro todavía no tiene generador.")
	if doc.status == "Queued":
		return {"status": doc.status, "generation_key": doc.generation_key}
	if doc.status == "Generated":
		return {"status": doc.status, "generation_key": doc.generation_key}
	if doc.status not in {"Draft", "Validation Failed", "Rejected"}:
		frappe.throw("La emisión no está disponible para generación.")
	if doc.preflight_status != "Passed":
		frappe.throw("Debe completar un preflight sin bloqueos antes de generar.")

	generation_key = frappe.generate_hash(length=32)
	if doc.status == "Rejected":
		doc.db_set("generation_number", (doc.generation_number or 1) + 1, update_modified=False)
		for field in (
			"reviewed_by",
			"reviewed_at",
			"review_comment",
			"rejected_by",
			"rejected_at",
			"rejection_reason",
		):
			doc.db_set(field, None, update_modified=False)
	doc.db_set("generation_key", generation_key, update_modified=False)
	doc.db_set("generation_progress", 0, update_modified=False)
	doc.db_set("generation_message", "En espera del worker", update_modified=False)
	doc.db_set("status", "Queued")
	frappe.enqueue(
		"contanext_guatemala.books.jobs.generate_book_run",
		queue="long",
		enqueue_after_commit=True,
		job_id=f"gt-books:{doc.name}:{generation_key}",
		deduplicate=True,
		book_run=doc.name,
		generation_key=generation_key,
	)
	return {"status": "Queued", "generation_key": generation_key}


@frappe.whitelist()
def submit_for_review(book_run: str) -> dict:
	doc = frappe.get_doc("GT Accounting Book Run", book_run)
	doc.check_permission("write")
	context = _transition_context(doc)
	validate_transition(doc.status, "Ready for Review", context)
	doc.db_set("status", "Ready for Review")
	_record_review_event(doc, "SUBMITTED_FOR_REVIEW")
	return {"status": "Ready for Review"}


@frappe.whitelist()
def review_book_run(book_run: str, comment: str | None = None) -> dict:
	doc = frappe.get_doc("GT Accounting Book Run", book_run)
	doc.check_permission("write")
	if doc.status != "Ready for Review" or doc.reviewed_by:
		frappe.throw("La emisión no está pendiente de revisión.")
	if "GT Books Reviewer" not in frappe.get_roles():
		frappe.throw("La revisión requiere el rol GT Books Reviewer.")
	if frappe.session.user == doc.prepared_by:
		frappe.throw("El preparador no puede revisar su propia emisión.")
	from frappe.utils import now_datetime

	doc.db_set("reviewed_by", frappe.session.user, update_modified=False)
	doc.db_set("reviewed_at", now_datetime(), update_modified=False)
	doc.db_set("review_comment", comment, update_modified=False)
	doc.reload()
	_record_review_event(doc, "REVIEWED", comment)
	return {"status": doc.status, "reviewed_by": doc.reviewed_by}


@frappe.whitelist()
def decide_book_run(book_run: str, decision: str, reason: str | None = None) -> dict:
	doc = frappe.get_doc("GT Accounting Book Run", book_run)
	doc.check_permission("write")
	if decision not in {"Approved", "Rejected"}:
		frappe.throw("Decisión de emisión desconocida.")
	if decision == "Rejected" and not (reason or "").strip():
		frappe.throw("El rechazo requiere un motivo.")
	validate_transition(doc.status, decision, _transition_context(doc))
	from frappe.utils import now_datetime

	now = now_datetime()
	if decision == "Approved":
		doc.db_set("approved_by", frappe.session.user, update_modified=False)
		doc.db_set("approved_at", now, update_modified=False)
	else:
		doc.db_set("rejected_by", frappe.session.user, update_modified=False)
		doc.db_set("rejected_at", now, update_modified=False)
		doc.db_set("rejection_reason", reason, update_modified=False)
	doc.db_set("status", decision)
	doc.reload()
	_record_review_event(doc, "APPROVED" if decision == "Approved" else "REJECTED", reason)
	return {"status": doc.status}


@frappe.whitelist()
def request_sealing(book_run: str, idempotency_key: str | None = None) -> dict:
	doc = frappe.get_doc("GT Accounting Book Run", book_run)
	doc.check_permission("write")
	if "GT Books Manager" not in frappe.get_roles():
		frappe.throw("El sellado técnico requiere el rol GT Books Manager.")
	if doc.status in {"Sealing", "Awaiting Print Confirmation"} and doc.sealing_key:
		return {"status": doc.status, "sealing_key": doc.sealing_key}
	key = (
		doc.sealing_key
		if doc.status == "Seal Failed" and doc.sealing_key
		else (idempotency_key or "").strip() or frappe.generate_hash(length=32)
	)
	context = _transition_context(doc)
	context = TransitionContext(
		actor=context.actor,
		prepared_by=context.prepared_by,
		reviewed_by=context.reviewed_by,
		roles=context.roles,
		idempotency_key=key,
		preflight_passed=context.preflight_passed,
	)
	validate_transition(doc.status, "Sealing", context)
	doc.db_set("sealing_key", key, update_modified=False)
	doc.db_set("status", "Sealing")
	doc.reload()
	_record_review_event(doc, "SEALING_REQUESTED")
	frappe.enqueue(
		"contanext_guatemala.books.sealing.seal_book_run",
		queue="long",
		enqueue_after_commit=True,
		job_id=f"gt-books-seal:{doc.name}:{key}",
		deduplicate=True,
		book_run=doc.name,
		sealing_key=key,
		requested_by=frappe.session.user,
	)
	return {"status": "Sealing", "sealing_key": key}


@frappe.whitelist()
def confirm_print(
	book_run: str,
	idempotency_key: str,
	success: int | str = 0,
	failed_pages: str | None = None,
	reason: str | None = None,
) -> dict:
	from frappe.utils import now_datetime
	from contanext_guatemala.books.folios import record_folio_event, validate_failed_pages

	doc = frappe.get_doc("GT Accounting Book Run", book_run)
	doc.check_permission("write")
	if "GT Books Manager" not in frappe.get_roles():
		frappe.throw("La confirmación física requiere el rol GT Books Manager.")
	allocation = frappe.get_doc("GT Book Folio Allocation", doc.folio_allocation)
	if frappe.db.exists("GT Book Folio Event", {"idempotency_key": idempotency_key}):
		return {"status": doc.status, "idempotent": True}
	is_success = str(success).lower() in {"1", "true", "yes"}
	if is_success:
		validate_transition(doc.status, "Sealed", _transition_context(doc))
		record_folio_event(allocation, "PRINT_CONFIRMED", idempotency_key)
		allocation.db_set("status", "Consumed", update_modified=False)
		doc.db_set("print_confirmed_by", frappe.session.user, update_modified=False)
		doc.db_set("print_confirmed_at", now_datetime(), update_modified=False)
		doc.db_set("status", "Sealed")
		doc.reload()
		_record_review_event(doc, "PRINT_CONFIRMED")
		_supersede_replaced_run(doc)
		return {"status": doc.status}
	if not (reason or "").strip():
		frappe.throw("Una excepción de impresión requiere motivo.")
	pages = validate_failed_pages(doc.pdf_page_count, json.loads(failed_pages or "[]"))
	if not pages:
		frappe.throw("Indique al menos una página afectada.")
	validate_transition(doc.status, "Print Exception", _transition_context(doc))
	record_folio_event(allocation, "PRINT_EXCEPTION", idempotency_key, failed_pages=pages, reason=reason)
	doc.db_set("print_exception_reason", reason, update_modified=False)
	doc.db_set("status", "Print Exception")
	doc.reload()
	_record_review_event(doc, "PRINT_EXCEPTION", reason)
	return {"status": doc.status, "failed_pages": pages}


@frappe.whitelist()
def authorize_exact_reprint(book_run: str, idempotency_key: str, reason: str) -> dict:
	from contanext_guatemala.books.folios import record_folio_event

	doc = frappe.get_doc("GT Accounting Book Run", book_run)
	doc.check_permission("write")
	if "GT Books Manager" not in frappe.get_roles():
		frappe.throw("El reintento requiere el rol GT Books Manager.")
	if not (reason or "").strip():
		frappe.throw("El reintento requiere motivo.")
	if frappe.db.exists("GT Book Folio Event", {"idempotency_key": idempotency_key}):
		return {"status": doc.status, "idempotent": True}
	validate_transition(doc.status, "Awaiting Print Confirmation", _transition_context(doc))
	allocation = frappe.get_doc("GT Book Folio Allocation", doc.folio_allocation)
	record_folio_event(allocation, "RETRY_AUTHORIZED", idempotency_key, reason=reason)
	doc.db_set("status", "Awaiting Print Confirmation")
	doc.reload()
	_record_review_event(doc, "RETRY_AUTHORIZED", reason)
	return {"status": doc.status, "pdf_sha256": doc.pdf_sha256}


def _transition_context(doc) -> TransitionContext:
	return TransitionContext(
		actor=frappe.session.user,
		prepared_by=doc.prepared_by,
		reviewed_by=doc.reviewed_by,
		roles=frozenset(frappe.get_roles()),
		preflight_passed=doc.preflight_status == "Passed",
	)


def _supersede_replaced_run(doc) -> None:
	if not doc.supersedes:
		return
	rows = frappe.db.sql(
		"SELECT name, status FROM `tabGT Accounting Book Run` WHERE name=%s FOR UPDATE",
		(doc.supersedes,),
		as_dict=True,
	)
	if not rows or rows[0].status != "Sealed":
		frappe.throw("La emisión anterior ya no está disponible para sustitución.")
	previous = frappe.get_doc("GT Accounting Book Run", doc.supersedes)
	validate_transition(previous.status, "Superseded", _transition_context(previous))
	previous.db_set("status", "Superseded")
	previous.reload()
	_record_review_event(
		previous,
		"SUPERSEDED",
		f"Sustituida técnicamente por {doc.name}: {doc.correction_reason}",
	)


def _record_review_event(doc, action: str, comment: str | None = None) -> None:
	from contanext_guatemala.books.audit import record_book_event

	record_book_event(doc, action, comment)
