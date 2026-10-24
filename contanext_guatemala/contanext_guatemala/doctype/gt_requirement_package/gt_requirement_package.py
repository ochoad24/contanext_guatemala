import frappe
from frappe.model.document import Document
from frappe.utils import getdate


class GTRequirementPackage(Document):
	def validate(self):
		if self.period_from and self.period_to and getdate(self.period_from) > getdate(self.period_to):
			frappe.throw("La fecha inicial no puede ser posterior a la fecha final.")
		if self.is_new():
			self.status = "Draft"
			return
		old = self.get_doc_before_save()
		if not old:
			return
		if old.status != self.status and not self.flags.get("controlled_transition"):
			frappe.throw("El estado solo puede cambiar mediante una acción controlada.")
		if old.status in {"Generated", "Released"}:
			protected = {
				"company", "request_reference", "period_from", "period_to", "purpose", "recipient",
				"package_file", "package_sha256", "manifest_sha256",
			}
			book_fields = (
				"book_run", "include_pdf", "include_csv", "include_manifest", "include_authorizations"
			)
			support_fields = ("document_type", "reference", "document_date", "description", "sha256")
			children_changed = (
				_child_values(self.book_runs, book_fields) != _child_values(old.book_runs, book_fields)
				or _child_values(self.support_index, support_fields)
				!= _child_values(old.support_index, support_fields)
			)
			if children_changed or any(self.get(field) != old.get(field) for field in protected):
				frappe.throw("Un paquete generado no se puede modificar.")

	def on_trash(self):
		if self.status in {"Generated", "Released"}:
			frappe.throw("Un paquete generado o liberado no se puede eliminar.")


def _child_values(rows, fields):
	return [tuple(row.get(field) for field in fields) for row in rows]


@frappe.whitelist()
def generate(package_name: str):
	from contanext_guatemala.books.requirements import generate_requirement_package

	return generate_requirement_package(package_name)


@frappe.whitelist()
def release(package_name: str):
	from contanext_guatemala.books.requirements import record_package_event

	doc = frappe.get_doc("GT Requirement Package", package_name)
	doc.check_permission("write")
	if "GT Books Manager" not in frappe.get_roles():
		frappe.throw("La liberación requiere el rol GT Books Manager.")
	if doc.status == "Released":
		return {"status": doc.status}
	if doc.status != "Generated":
		frappe.throw("Solo se puede liberar un paquete generado.")
	doc.released_by = frappe.session.user
	doc.released_at = frappe.utils.now_datetime()
	doc.status = "Released"
	doc.flags.controlled_transition = True
	doc.save(ignore_permissions=True)
	record_package_event(doc, "RELEASED")
	return {"status": doc.status}


@frappe.whitelist()
def download(package_name: str):
	from contanext_guatemala.books.requirements import audit_package_download

	audit_package_download(package_name)
