import frappe
from frappe.model.document import Document


class GTRequirementPackageEvent(Document):
	def on_trash(self):
		frappe.throw("Los eventos de paquete son inmutables.")

	def before_save(self):
		if not self.is_new():
			frappe.throw("Los eventos de paquete son inmutables.")
