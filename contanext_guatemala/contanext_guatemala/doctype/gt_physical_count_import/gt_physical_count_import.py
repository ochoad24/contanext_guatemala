import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

from contanext_guatemala.books.physical_counts import TEMPLATE_VERSION, parse_physical_count, sha256_hex


PROTECTED_FIELDS = {
	"company", "cutoff_date", "template_version", "source_file", "file_sha256", "file_size",
	"accepted_rows", "rejected_rows", "rows", "stock_reconciliation",
}


class GTPhysicalCountImport(Document):
	def before_insert(self) -> None:
		self.uploaded_by = frappe.session.user
		self.status = "Draft"
		self.template_version = TEMPLATE_VERSION

	def validate(self) -> None:
		self.template_version = TEMPLATE_VERSION
		self._prevent_direct_status_change()
		content, filename = self._private_file()
		old = self.get_doc_before_save() if not self.is_new() else None
		current_hash = sha256_hex(content)
		if self.is_new() or not old or old.source_file != self.source_file or old.file_sha256 != current_hash:
			self._parse(content, filename)
		self._prevent_approved_mutation()
		self._validate_stock_reconciliation()

	def on_trash(self) -> None:
		if self.status == "Approved" or frappe.db.exists(
			"GT Accounting Book Run", {"physical_count_import": self.name}
		):
			frappe.throw("Un conteo aprobado o vinculado a una emisión no se puede eliminar.")

	def _private_file(self) -> tuple[bytes, str]:
		file_name = frappe.db.get_value("File", {"file_url": self.source_file}, "name")
		if not file_name:
			frappe.throw("El conteo debe apuntar a un archivo registrado en ContaNext.")
		file_doc = frappe.get_doc("File", file_name)
		if not file_doc.is_private:
			frappe.throw("El archivo original del conteo debe ser privado.")
		return file_doc.get_content(), file_doc.file_name

	def _parse(self, content: bytes, filename: str) -> None:
		try:
			parsed = parse_physical_count(content, filename)
		except ValueError as error:
			frappe.throw(str(error))
		self.set("rows", [])
		seen = set()
		for source in parsed:
			status, error = source.status, source.error
			key = (source.item_code, source.warehouse)
			if status == "Accepted" and key in seen:
				status, error = "Rejected", "artículo y bodega duplicados"
			if status == "Accepted":
				error = self._master_error(source)
				status = "Rejected" if error else "Accepted"
			if status == "Accepted":
				seen.add(key)
			self.append(
				"rows",
				{
					"source_row": source.source_row,
					"status": status,
					"item_code": source.item_code,
					"warehouse": source.warehouse,
					"uom": source.uom,
					"counted_quantity": source.counted_quantity,
					"note": source.note,
					"error": error,
				},
			)
		self.file_sha256 = sha256_hex(content)
		self.file_size = len(content)
		self.accepted_rows = sum(row.status == "Accepted" for row in self.rows)
		self.rejected_rows = sum(row.status == "Rejected" for row in self.rows)

	def _master_error(self, row) -> str:
		item = frappe.db.get_value("Item", row.item_code, ["stock_uom", "is_stock_item"], as_dict=True)
		if not item or not item.is_stock_item:
			return "el artículo no existe o no es de inventario"
		warehouse = frappe.db.get_value("Warehouse", row.warehouse, ["company", "is_group"], as_dict=True)
		if not warehouse or warehouse.company != self.company or warehouse.is_group:
			return "la bodega no pertenece a la empresa o es agrupadora"
		if item.stock_uom != row.uom:
			return "la unidad no coincide con la unidad de inventario"
		return ""

	def _validate_stock_reconciliation(self) -> None:
		if not self.stock_reconciliation:
			return
		reconciliation = frappe.db.get_value(
			"Stock Reconciliation", self.stock_reconciliation, ["company", "posting_date", "docstatus"], as_dict=True
		)
		if not reconciliation or reconciliation.company != self.company:
			frappe.throw("Stock Reconciliation debe pertenecer a la misma empresa.")
		if reconciliation.docstatus != 1 or getdate(reconciliation.posting_date) != getdate(self.cutoff_date):
			frappe.throw("Stock Reconciliation debe estar enviado y usar la misma fecha de corte.")

	def _prevent_direct_status_change(self) -> None:
		old = self.get_doc_before_save() if not self.is_new() else None
		if old and old.status != self.status and not getattr(self.flags, "controlled_transition", False):
			frappe.throw("El estado del conteo solo cambia mediante una decisión controlada.")

	def _prevent_approved_mutation(self) -> None:
		old = self.get_doc_before_save() if not self.is_new() else None
		if old and old.status == "Approved" and any(self.get(field) != old.get(field) for field in PROTECTED_FIELDS):
			frappe.throw("Un conteo físico aprobado es inmutable; cargue una nueva versión.")


@frappe.whitelist()
def decide_physical_count(import_name: str, decision: str, reason: str | None = None) -> dict:
	doc = frappe.get_doc("GT Physical Count Import", import_name)
	doc.check_permission("write")
	if "GT Books Reviewer" not in frappe.get_roles() and "GT Books Manager" not in frappe.get_roles():
		frappe.throw("La decisión requiere el rol GT Books Reviewer o GT Books Manager.")
	if doc.uploaded_by == frappe.session.user:
		frappe.throw("La persona que cargó el conteo no puede aprobarlo ni rechazarlo.")
	if doc.status != "Draft" or decision not in {"Approved", "Rejected"}:
		frappe.throw("La decisión solicitada no está disponible.")
	if decision == "Approved" and (not doc.accepted_rows or doc.rejected_rows):
		frappe.throw("Para aprobar, el archivo debe tener filas aceptadas y ninguna rechazada.")
	if decision == "Rejected" and not (reason or "").strip():
		frappe.throw("El rechazo requiere un motivo.")
	doc.flags.controlled_transition = True
	doc.status = decision
	doc.approved_by = frappe.session.user if decision == "Approved" else None
	doc.approved_at = now_datetime() if decision == "Approved" else None
	doc.rejection_reason = reason if decision == "Rejected" else None
	doc.save()
	return {"status": doc.status, "sha256": doc.file_sha256}
