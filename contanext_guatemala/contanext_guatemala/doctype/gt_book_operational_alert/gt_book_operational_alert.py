import frappe
from frappe.model.document import Document


class GTBookOperationalAlert(Document):
	def validate(self):
		if self.is_new():
			self.status = "Open"
			return
		old = self.get_doc_before_save()
		if old and any(self.get(field) != old.get(field) for field in ("company", "book_run", "category", "detected_at", "fingerprint", "evidence_json")):
			frappe.throw("La evidencia de una alerta operativa es inmutable.")

	def on_trash(self):
		frappe.throw("Las alertas operativas no se eliminan; deben atenderse o cerrarse.")


@frappe.whitelist()
def resolve(alert_name: str, resolution: str):
	doc = frappe.get_doc("GT Book Operational Alert", alert_name)
	doc.check_permission("write")
	if "GT Books Manager" not in frappe.get_roles():
		frappe.throw("Cerrar una alerta requiere el rol GT Books Manager.")
	if not (resolution or "").strip():
		frappe.throw("La resolución es obligatoria.")
	doc.status = "Resolved"
	doc.resolution = resolution.strip()
	doc.resolved_by = frappe.session.user
	doc.resolved_at = frappe.utils.now_datetime()
	doc.save(ignore_permissions=True)
	return {"status": doc.status}
