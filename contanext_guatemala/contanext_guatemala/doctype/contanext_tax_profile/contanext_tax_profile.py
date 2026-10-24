import re

import frappe
from frappe.model.document import Document
from frappe.utils import cint


class ContaNextTaxProfile(Document):
	def validate(self) -> None:
		self.nit = normalize_nit(self.nit)
		if self.nit and not is_structurally_valid_nit(self.nit):
			frappe.throw("El NIT solo puede contener dígitos, guion y un dígito verificador numérico o K.")
		if cint(self.is_default) and not self.company:
			frappe.throw("Un perfil fiscal predeterminado debe indicar una empresa.")


def normalize_nit(value: str | None) -> str:
	return re.sub(r"\s+", "", (value or "").upper())


def is_structurally_valid_nit(value: str) -> bool:
	"""Validate syntax only; SAT verification belongs to an authorized integration."""
	return bool(re.fullmatch(r"\d{1,12}-?[\dK]", value))
