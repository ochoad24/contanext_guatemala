from __future__ import annotations

from frappe.model.document import Document

from contanext_guatemala.validation import validate_nit_format


class ContaNextFiscalSettings(Document):
	def validate(self) -> None:
		self.nit = validate_nit_format(self.nit)
