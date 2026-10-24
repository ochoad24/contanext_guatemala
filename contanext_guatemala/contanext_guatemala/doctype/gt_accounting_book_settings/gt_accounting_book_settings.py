import frappe
from frappe.model.document import Document

from contanext_guatemala.books.constants import UNAUTHORIZED_DRAFT_LABEL


class GTAccountingBookSettings(Document):
	def validate(self) -> None:
		self.draft_notice = UNAUTHORIZED_DRAFT_LABEL
		self.legal_format_version = "PROTOTYPE-1"
		self._validate_unique_company()
		self._validate_profile()
		self._validate_inventory_mappings()
		if self.book_currency != "GTQ":
			frappe.throw("La moneda de libros debe ser GTQ.")
		if self.language != "Español":
			frappe.throw("El idioma de libros debe ser Español.")
		if self.enabled:
			self._validate_profile_complete()

	def _validate_unique_company(self) -> None:
		filters = {"company": self.company, "name": ["!=", self.name or ""]}
		if self.company and frappe.db.exists("GT Accounting Book Settings", filters):
			frappe.throw("Ya existe una configuración de libros para esta empresa.")

	def _validate_profile(self) -> None:
		profile_company = frappe.db.get_value(
			"ContaNext Tax Profile", self.tax_profile, "company"
		)
		if self.tax_profile and profile_company != self.company:
			frappe.throw("El perfil fiscal debe pertenecer a la misma empresa.")

	def _validate_profile_complete(self) -> None:
		profile = frappe.get_cached_doc("ContaNext Tax Profile", self.tax_profile)
		required = {
			"fiscal_name_for_books": "Nombre fiscal para libros",
			"fiscal_establishment": "Establecimiento fiscal",
			"accounting_framework": "Marco contable",
			"legal_representative_name": "Representante legal",
			"accountant_name": "Contador",
			"accountant_nit": "NIT del contador",
		}
		missing = [label for fieldname, label in required.items() if not profile.get(fieldname)]
		if missing:
			frappe.throw("Complete el perfil fiscal antes de habilitar borradores: " + ", ".join(missing))

	def _validate_inventory_mappings(self) -> None:
		seen = set()
		for row in self.inventory_account_mappings:
			required = {
				"WAREHOUSE": ("warehouse",),
				"ITEM": ("item_code",),
				"ITEM_GROUP": ("item_group",),
				"ITEM_WAREHOUSE": ("item_code", "warehouse"),
			}.get(row.scope_type)
			if not required or any(not row.get(field) for field in required):
				frappe.throw(f"El mapeo de inventario #{row.idx} no tiene completo su alcance explícito.")
			unused = {"warehouse", "item_code", "item_group"} - set(required)
			if any(row.get(field) for field in unused):
				frappe.throw(f"El mapeo de inventario #{row.idx} contiene selectores fuera de su alcance.")
			selector = (row.scope_type,) + tuple(row.get(field) for field in required)
			if selector in seen:
				frappe.throw("No se permiten dos mapeos con el mismo alcance de inventario.")
			seen.add(selector)
			account = frappe.db.get_value(
				"Account", row.inventory_account, ["company", "root_type", "account_type", "is_group"], as_dict=True
			)
			if not account or account.company != self.company or account.is_group or account.root_type != "Asset":
				frappe.throw(f"La cuenta del mapeo #{row.idx} debe ser una cuenta de activo no agrupadora de la empresa.")
			if account.account_type != "Stock":
				frappe.throw(f"La cuenta del mapeo #{row.idx} debe tener tipo de cuenta Stock.")
			if row.warehouse and frappe.db.get_value("Warehouse", row.warehouse, "company") != self.company:
				frappe.throw(f"La bodega del mapeo #{row.idx} no pertenece a la empresa.")
			if row.item_code and not frappe.db.get_value("Item", row.item_code, "is_stock_item"):
				frappe.throw(f"El artículo del mapeo #{row.idx} debe ser un artículo de inventario.")

	def on_trash(self) -> None:
		if frappe.db.exists("GT Accounting Book Run", {"company": self.company}):
			frappe.throw("No se puede eliminar una configuración que ya tiene emisiones.")
