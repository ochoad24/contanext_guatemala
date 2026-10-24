import frappe
from frappe.model.document import Document


class GTBookReviewEvent(Document):
	def validate(self) -> None:
		if not self.is_new():
			frappe.throw("Los eventos de revisión son inmutables.")

	def on_trash(self) -> None:
		frappe.throw("Los eventos de revisión no se pueden eliminar.")
