import frappe
from frappe.model.document import Document

from contanext_guatemala.books.constants import UNAUTHORIZED_DRAFT_LABEL
from contanext_guatemala.fiscal.company import get_company_fiscal_configuration
from contanext_guatemala.validation import validate_nit_format


class GTAccountingBookSettings(Document):
	def validate(self) -> None:
		self.draft_notice = UNAUTHORIZED_DRAFT_LABEL
		self.legal_format_version = "PROTOTYPE-1"
		self._validate_unique_company()
		self._validate_inventory_mappings()
		if self.book_currency != "GTQ":
			frappe.throw("La moneda de libros debe ser GTQ.")
		if self.language != "Español":
			frappe.throw("El idioma de libros debe ser Español.")
		if self.enabled:
			self._validate_company_fiscal_configuration()

	def _validate_unique_company(self) -> None:
		filters = {"company": self.company, "name": ["!=", self.name or ""]}
		if self.company and frappe.db.exists("GT Accounting Book Settings", filters):
			frappe.throw("Ya existe una configuración de libros para esta empresa.")

	def _validate_company_fiscal_configuration(self) -> None:
		configuration = get_company_fiscal_configuration(self.company)
		required = {
			"legal_name": "Razón social",
			"nit": "NIT",
			"fiscal_address": "Dirección fiscal",
			"establishment_code": "Código de establecimiento fiscal",
			"accounting_framework": "Marco contable",
			"legal_representative_name": "Representante legal",
			"accountant_name": "Contador",
			"accountant_nit": "NIT del contador",
		}
		missing = [
			label for fieldname, label in required.items() if not getattr(configuration, fieldname)
		]
		if missing:
			frappe.throw(
				"Complete la configuración fiscal de la empresa antes de habilitar borradores: "
				+ ", ".join(missing)
			)
		if configuration.country != "Guatemala":
			frappe.throw("Los Libros contables GT solo pueden habilitarse para una empresa de Guatemala.")
		if configuration.currency != "GTQ":
			frappe.throw("La moneda predeterminada de la empresa debe ser GTQ para habilitar Libros contables GT.")
		try:
			validate_nit_format(configuration.nit)
			validate_nit_format(configuration.accountant_nit)
		except ValueError:
			frappe.throw("El NIT de la empresa o del contador tiene un formato inválido.")

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
