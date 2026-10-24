import frappe
from frappe.model.document import Document


class GTBookFolioEvent(Document):
	def on_trash(self) -> None:
		frappe.throw("Los eventos de folios son inmutables.")

	def validate(self) -> None:
		if not self.is_new():
			frappe.throw("Los eventos de folios son inmutables.")
