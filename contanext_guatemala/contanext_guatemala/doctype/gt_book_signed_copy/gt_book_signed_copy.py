import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from contanext_guatemala.books.pdf_validation import validate_pdf


class GTBookSignedCopy(Document):
	def before_insert(self) -> None:
		if "GT Books Manager" not in frappe.get_roles():
			frappe.throw("Solo GT Books Manager puede adjuntar una copia firmada.")
		run = frappe.get_doc("GT Accounting Book Run", self.book_run)
		if run.status not in {"Awaiting Print Confirmation", "Print Exception", "Sealed"}:
			frappe.throw("La emisión todavía no tiene un PDF exacto para impresión.")
		self.company = run.company
		file_doc = frappe.get_doc("File", {"file_url": self.signed_pdf})
		if not file_doc.is_private:
			frappe.throw("La copia firmada debe ser privada.")
		content = file_doc.get_content()
		if isinstance(content, str):
			content = content.encode()
		self.sha256 = validate_pdf(content).sha256
		self.uploaded_by = frappe.session.user
		self.uploaded_at = now_datetime()

	def after_insert(self) -> None:
		from contanext_guatemala.books.audit import record_book_event

		record_book_event(frappe.get_doc("GT Accounting Book Run", self.book_run), "SIGNED_COPY_ATTACHED")

	def validate(self) -> None:
		if not self.is_new():
			frappe.throw("Una copia firmada registrada es inmutable; adjunte una nueva versión.")

	def on_trash(self) -> None:
		frappe.throw("Una copia firmada registrada no se puede eliminar.")
