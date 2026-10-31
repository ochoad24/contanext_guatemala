import frappe
from frappe.model.document import Document


class GTFELOperationEvent(Document):
	def before_save(self):
		if not self.is_new():
			frappe.throw(frappe._("Los eventos FEL son inmutables."))

	def on_trash(self):
		frappe.throw(frappe._("Los eventos FEL no se pueden eliminar."))
