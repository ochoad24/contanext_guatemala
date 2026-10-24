import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime
from pypdf.errors import PdfReadError

from contanext_guatemala.books.pdf_validation import validate_pdf


PROTECTED_FIELDS = {
	"company", "title", "annex_type", "period_from", "period_to", "version", "display_order", "pdf_file",
	"sha256", "page_count", "size_bytes", "security_scan_status",
}


class GTFinancialStatementAnnex(Document):
	def before_insert(self) -> None:
		self.authored_by = frappe.session.user
		self.status = "Draft"

	def validate(self) -> None:
		if self.period_from and self.period_to and getdate(self.period_from) > getdate(self.period_to):
			frappe.throw("La fecha inicial del anexo no puede ser posterior a la final.")
		self._prevent_direct_status_change()
		self._prevent_approved_mutation()
		self._validate_private_pdf()

	def on_trash(self) -> None:
		if self.status == "Approved" or frappe.db.exists("GT Book Run Annex", {"annex": self.name}):
			frappe.throw("Un anexo aprobado o vinculado a una emisión no se puede eliminar.")

	def _prevent_direct_status_change(self) -> None:
		old = self.get_doc_before_save() if not self.is_new() else None
		if old and old.status != self.status and not getattr(self.flags, "controlled_transition", False):
			frappe.throw("El estado del anexo solo puede cambiar mediante aprobación o rechazo controlado.")

	def _prevent_approved_mutation(self) -> None:
		old = self.get_doc_before_save() if not self.is_new() else None
		if old and old.status == "Approved" and any(self.get(field) != old.get(field) for field in PROTECTED_FIELDS):
			frappe.throw("Un anexo aprobado es inmutable; cree una nueva versión.")

	def _validate_private_pdf(self) -> None:
		file_name = frappe.db.get_value("File", {"file_url": self.pdf_file}, "name")
		if not file_name:
			frappe.throw("El anexo debe apuntar a un archivo registrado en ContaNext.")
		file_doc = frappe.get_doc("File", file_name)
		if not file_doc.is_private:
			frappe.throw("El anexo debe almacenarse como archivo privado.")
		try:
			validation = validate_pdf(file_doc.get_content())
		except (ValueError, OSError, PdfReadError) as error:
			frappe.throw(str(error))
		self.sha256 = validation.sha256
		self.page_count = validation.page_count
		self.size_bytes = validation.size_bytes
		self.security_scan_status = validation.security_status


@frappe.whitelist()
def decide_annex(annex: str, decision: str, reason: str | None = None) -> dict:
	doc = frappe.get_doc("GT Financial Statement Annex", annex)
	doc.check_permission("write")
	if "GT Books Reviewer" not in frappe.get_roles() and "GT Books Manager" not in frappe.get_roles():
		frappe.throw("La decisión requiere el rol GT Books Reviewer o GT Books Manager.")
	if doc.authored_by == frappe.session.user:
		frappe.throw("El autor no puede aprobar ni rechazar su propio anexo.")
	if doc.status != "Draft" or decision not in {"Approved", "Rejected"}:
		frappe.throw("La decisión solicitada no está disponible.")
	if decision == "Rejected" and not (reason or "").strip():
		frappe.throw("El rechazo requiere un motivo.")
	doc.flags.controlled_transition = True
	doc.status = decision
	doc.approved_by = frappe.session.user if decision == "Approved" else None
	doc.approved_at = now_datetime() if decision == "Approved" else None
	doc.rejection_reason = reason if decision == "Rejected" else None
	doc.save()
	return {"status": doc.status, "sha256": doc.sha256}
