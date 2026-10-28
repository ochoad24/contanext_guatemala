PROTECTED_RUN_STATUSES = {
	"Generated",
	"Ready for Review",
	"Approved",
	"Sealing",
	"Awaiting Print Confirmation",
	"Print Exception",
	"Sealed",
	"Seal Failed",
	"Superseded",
}

CONTROLLED_FILE_PARENTS = {
	"GT Accounting Book Run",
	"GT Book Authorization Evidence",
	"GT Financial Statement Annex",
	"GT Physical Count Import",
	"GT Book Signed Copy",
	"GT Requirement Package",
}


def protect_book_file_before_save(doc, method=None) -> None:
	import frappe

	if doc.attached_to_doctype in CONTROLLED_FILE_PARENTS and not doc.is_private:
		frappe.throw("Los archivos de libros contables deben almacenarse como privados.")
	if doc.attached_to_doctype == "GT Requirement Package" and doc.attached_to_name:
		status = frappe.db.get_value("GT Requirement Package", doc.attached_to_name, "status")
		if status in {"Generated", "Released"} and not doc.is_new():
			old = doc.get_doc_before_save()
			protected = {"file_url", "content_hash", "file_size", "is_private", "attached_to_doctype", "attached_to_name"}
			if old and any(doc.get(field) != old.get(field) for field in protected):
				frappe.throw("Un paquete generado no se puede reemplazar ni volver público.")
		return
	if doc.is_new() or doc.attached_to_doctype != "GT Accounting Book Run" or not doc.attached_to_name:
		return
	status = frappe.db.get_value("GT Accounting Book Run", doc.attached_to_name, "status")
	if status not in PROTECTED_RUN_STATUSES:
		return
	old = doc.get_doc_before_save()
	protected = {"file_url", "content_hash", "file_size", "is_private", "attached_to_doctype", "attached_to_name"}
	if old and any(doc.get(field) != old.get(field) for field in protected):
		frappe.throw("Un archivo de una emisión generada no se puede reemplazar ni volver público.")


def protect_book_file_on_trash(doc, method=None) -> None:
	import frappe

	if doc.attached_to_doctype == "GT Requirement Package" and doc.attached_to_name:
		status = frappe.db.get_value("GT Requirement Package", doc.attached_to_name, "status")
		if status in {"Generated", "Released"}:
			frappe.throw("Un paquete generado o liberado no se puede eliminar.")
		return
	if doc.attached_to_doctype != "GT Accounting Book Run" or not doc.attached_to_name:
		return
	status = frappe.db.get_value("GT Accounting Book Run", doc.attached_to_name, "status")
	if status in PROTECTED_RUN_STATUSES:
		frappe.throw("Un archivo de una emisión generada no se puede eliminar.")


def restrict_controlled_book_file(doc, user=None, ptype=None, permission_type=None, debug=False):
	"""Authorize private files through their company-scoped parent object.

	Requirement packages are stricter: their bytes are only available through the
	audited download endpoint, never through a direct File URL.

	Frappe treats every falsy hook result, including ``None``, as an explicit
	denial. Return ``True`` when this controller does not need to restrict the
	operation so normal File permissions remain authoritative.
	"""
	permission_type = ptype or permission_type
	if permission_type != "read":
		return True
	if doc.attached_to_doctype == "GT Requirement Package":
		return False
	if doc.attached_to_doctype not in CONTROLLED_FILE_PARENTS:
		return True
	if not doc.attached_to_name:
		return False
	import frappe

	return bool(
		frappe.has_permission(
			doc.attached_to_doctype,
			"read",
			doc=doc.attached_to_name,
			user=user,
		)
	)
