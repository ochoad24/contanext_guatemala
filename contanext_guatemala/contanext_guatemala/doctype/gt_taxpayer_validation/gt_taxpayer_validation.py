import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime

from contanext_guatemala.fel.taxpayer import normalize_taxpayer_identifier, taxpayer_lookup_key


class GTTaxpayerValidation(Document):
	def validate(self):
		self.provider = (self.provider or "").strip().upper()
		self.environment = (self.environment or "").strip().upper()
		self.identification_type = (self.identification_type or "").strip().upper()
		self.normalized_identifier = normalize_taxpayer_identifier(
			self.identification_type, self.normalized_identifier or self.identifier
		)
		self.lookup_key = taxpayer_lookup_key(
			self.provider, self.environment, self.identification_type, self.normalized_identifier
		)
		self.queried_at = self.queried_at or now_datetime()
		self.requested_by = self.requested_by or frappe.session.user
		self.validate_current_uniqueness()
		self.validate_previous_result()

	def validate_current_uniqueness(self):
		if not self.is_current:
			return
		filters = {"lookup_key": self.lookup_key, "is_current": 1, "name": ["!=", self.name or ""]}
		if frappe.db.exists("GT Taxpayer Validation", filters):
			frappe.throw(frappe._("Ya existe una validación tributaria vigente para esta clave."))

	def validate_previous_result(self):
		if not self.previous_validation:
			return
		previous_key = frappe.db.get_value("GT Taxpayer Validation", self.previous_validation, "lookup_key")
		if previous_key and previous_key != self.lookup_key:
			frappe.throw(frappe._("La validación anterior debe corresponder a la misma clave tributaria."))
