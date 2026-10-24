import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime


class GTBookAuthorizationEvidence(Document):
	def validate(self) -> None:
		self.controls_sequence = 0
		self.legal_notice = "No habilita sellado ni prueba cumplimiento mientras ADR-002 permanezca provisional."
		if self.effective_from and self.effective_to and getdate(self.effective_from) > getdate(self.effective_to):
			frappe.throw("La vigencia inicial no puede ser posterior a la final.")
		self._validate_private_file()
		self._validate_verification()
		self._prevent_used_evidence_mutation()

	def _validate_private_file(self) -> None:
		if not self.resolution_file:
			return
		is_private = frappe.db.get_value("File", {"file_url": self.resolution_file}, "is_private")
		if is_private is None:
			frappe.throw("La evidencia debe apuntar a un archivo registrado en ContaNext.")
		if not is_private:
			frappe.throw("La evidencia de autorización debe almacenarse como archivo privado.")

	def _validate_verification(self) -> None:
		previous_status = self.get_db_value("status") if not self.is_new() else None
		if self.status == "Verified" and previous_status != "Verified":
			if "GT Books Manager" not in frappe.get_roles():
				frappe.throw("Solo GT Books Manager puede verificar evidencias.")
			self.verified_by = frappe.session.user
			self.verified_at = now_datetime()
		if previous_status == "Verified" and self.status == "Draft":
			frappe.throw("Una evidencia verificada no puede volver a borrador.")

	def on_trash(self) -> None:
		if frappe.db.exists("GT Book Run Authorization", {"authorization_evidence": self.name}):
			frappe.throw("No se puede eliminar una evidencia vinculada a una emisión.")

	def _prevent_used_evidence_mutation(self) -> None:
		if self.is_new() or not frappe.db.exists(
			"GT Book Run Authorization", {"authorization_evidence": self.name}
		):
			return
		old = self.get_doc_before_save()
		protected = {
			"company",
			"authority",
			"book_type",
			"mode",
			"resolution_number",
			"resolution_date",
			"establishment_code",
			"resolution_file",
			"quantity_as_stated",
			"unit_as_stated",
			"range_as_stated",
		}
		if old and any(self.get(field) != old.get(field) for field in protected):
			frappe.throw("Una evidencia vinculada no puede cambiar; registre una nueva versión.")
