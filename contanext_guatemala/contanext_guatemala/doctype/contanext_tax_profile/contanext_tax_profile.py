import re

import frappe
from frappe.model.document import Document
from frappe.utils import cint


class ContaNextTaxProfile(Document):
	def validate(self) -> None:
		self.nit = normalize_nit(self.nit)
		self.accountant_nit = normalize_nit(self.accountant_nit)
		if self.nit and not is_structurally_valid_nit(self.nit):
			frappe.throw("El NIT solo puede contener dígitos, guion y un dígito verificador numérico o K.")
		if self.accountant_nit and not is_structurally_valid_nit(self.accountant_nit):
			frappe.throw("El NIT del contador tiene una estructura inválida.")
		if cint(self.is_default) and not self.company:
			frappe.throw("Un perfil fiscal predeterminado debe indicar una empresa.")
		if self.fiscal_year_start_month and not 1 <= cint(self.fiscal_year_start_month) <= 12:
			frappe.throw("El mes inicial del ejercicio debe estar entre 1 y 12.")
		if self.book_currency and self.book_currency != "GTQ":
			frappe.throw("La moneda de libros para la localización de Guatemala debe ser GTQ.")
		if self.book_language and self.book_language != "Español":
			frappe.throw("El idioma de libros debe ser Español.")


def normalize_nit(value: str | None) -> str:
	return re.sub(r"\s+", "", (value or "").upper())


def is_structurally_valid_nit(value: str) -> bool:
	"""Validate syntax only; SAT verification belongs to an authorized integration."""
	return bool(re.fullmatch(r"\d{1,12}-?[\dK]", value))
