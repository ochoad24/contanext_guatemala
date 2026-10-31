import frappe
from frappe.model.document import Document


ALLOWED_TRANSITIONS = {
	"PENDING": frozenset({"PROCESSING", "FAILED"}),
	"PROCESSING": frozenset(
		{"CERTIFIED", "REJECTED", "RETRY_PENDING", "RECONCILIATION_REQUIRED", "CANCEL_PENDING", "CANCELLED", "FAILED"}
	),
	"RETRY_PENDING": frozenset({"PROCESSING", "FAILED"}),
	"RECONCILIATION_REQUIRED": frozenset({"PROCESSING", "CERTIFIED", "CANCELLED", "FAILED"}),
	"CERTIFIED": frozenset(),
	"REJECTED": frozenset(),
	"CANCEL_PENDING": frozenset({"PROCESSING", "CANCELLED", "RECONCILIATION_REQUIRED", "FAILED"}),
	"CANCELLED": frozenset(),
	"FAILED": frozenset({"PROCESSING"}),
}
IMMUTABLE_SNAPSHOT_FIELDS = (
	"company",
	"document_type",
	"source_doctype",
	"source_name",
	"operation",
	"provider",
	"environment",
	"idempotency_key",
	"canonical_hash",
	"original_operation",
	"issuer_snapshot",
	"receiver_snapshot",
	"establishment_snapshot",
	"source_snapshot",
)


class FELOperation(Document):
	def validate(self):
		self.validate_source_company()
		self.validate_state_transition()
		self.validate_operation_links()
		self.validate_immutable_snapshot()

	def validate_source_company(self):
		"""Prevent an FEL operation from crossing company boundaries."""
		if not self.company or not self.source_doctype or not self.source_name:
			return

		source = frappe.get_doc(self.source_doctype, self.source_name)
		source_company = source.name if source.doctype == "Company" else source.get("company")

		if not source_company:
			frappe.throw(
				frappe._("El documento origen {0} no define una empresa.").format(
					frappe.bold(f"{self.source_doctype} {self.source_name}")
				)
			)

		if source_company != self.company:
			frappe.throw(
				frappe._(
					"El documento origen pertenece a la empresa {0}, no a la empresa {1} de la operación FEL."
				).format(frappe.bold(source_company), frappe.bold(self.company))
			)

	def validate_state_transition(self):
		if self.is_new():
			if self.status != "PENDING":
				frappe.throw(frappe._("Una operación FEL nueva debe iniciar en PENDING."))
			return

		previous = self.get_doc_before_save()
		if not previous or previous.status == self.status:
			return
		if self.status not in ALLOWED_TRANSITIONS.get(previous.status, frozenset()):
			frappe.throw(
				frappe._("La transición FEL de {0} a {1} no está permitida.").format(
					frappe.bold(previous.status), frappe.bold(self.status)
				)
			)

	def validate_operation_links(self):
		if self.operation in {"CANCEL", "RECONCILE"} and not self.original_operation:
			frappe.throw(frappe._("La operación original es obligatoria para cancelar o reconciliar."))
		if self.original_operation == self.name:
			frappe.throw(frappe._("Una operación FEL no puede referenciarse a sí misma."))

	def validate_immutable_snapshot(self):
		if self.is_new():
			return
		previous = self.get_doc_before_save()
		if not previous:
			return
		changed = [field for field in IMMUTABLE_SNAPSHOT_FIELDS if self.get(field) != previous.get(field)]
		if changed:
			frappe.throw(
				frappe._("El snapshot de una operación FEL es inmutable. Campos: {0}.").format(
					", ".join(changed)
				)
			)
