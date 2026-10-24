import frappe
from frappe.model.document import Document


class GTBookFolioAllocation(Document):
	def validate(self) -> None:
		if not self.technical_simulation:
			frappe.throw("El consumo legal permanece bloqueado mientras ADR-002 esté provisional.")
		if self.print_mode != "SIMPLEX":
			frappe.throw("DUPLEX permanece bloqueado hasta cerrar G1 y G4.")
		if self.first_folio < 1 or self.last_folio - self.first_folio + 1 != self.folio_count:
			frappe.throw("El rango de folios simulado no es contiguo.")
		if not self.is_new():
			old = self.get_doc_before_save()
			if old and any(self.get(field) != old.get(field) for field in self.meta.get_valid_columns()):
				frappe.throw("Una asignación de folios es append-only.")

	def on_trash(self) -> None:
		frappe.throw("Una asignación de folios no se puede eliminar.")
