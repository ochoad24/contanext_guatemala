import frappe
from frappe.model.document import Document


class GTFELEstablishment(Document):
	def validate(self):
		self.establishment_code = (self.establishment_code or "").strip()
		self.validate_dates()
		self.validate_address_company()
		self.validate_unique_code()
		self.validate_default()

	def validate_dates(self):
		if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
			frappe.throw(frappe._("La fecha final de vigencia no puede ser anterior a la inicial."))

	def validate_address_company(self):
		if not self.address or not self.company:
			return
		if not frappe.db.exists(
			"Dynamic Link",
			{
				"parenttype": "Address",
				"parent": self.address,
				"link_doctype": "Company",
				"link_name": self.company,
			},
		):
			frappe.throw(frappe._("La dirección del establecimiento debe pertenecer a la misma empresa."))

	def validate_unique_code(self):
		filters = {"company": self.company, "establishment_code": self.establishment_code}
		existing = frappe.db.get_value("GT FEL Establishment", filters, "name")
		if existing and (self.is_new() or existing != self.name):
			frappe.throw(frappe._("El código de establecimiento ya existe para esta empresa."))

	def validate_default(self):
		if not self.is_default:
			return
		if not self.is_active:
			frappe.throw(frappe._("El establecimiento predeterminado debe estar activo."))
		filters = {"company": self.company, "is_default": 1, "name": ["!=", self.name or ""]}
		if frappe.db.exists("GT FEL Establishment", filters):
			frappe.throw(frappe._("Solo puede existir un establecimiento predeterminado por empresa."))
