import frappe
from frappe.tests.utils import FrappeTestCase

from contanext_guatemala.fel.artifacts import record_fel_event


class TestFELOperationSnapshot(FrappeTestCase):
	def _operation(self):
		company = frappe.get_all("Company", pluck="name", limit=1)[0]
		return frappe.get_doc(
			{
				"doctype": "FEL Operation",
				"company": company,
				"document_type": "FACT",
				"source_doctype": "Company",
				"source_name": company,
				"operation": "CERTIFY",
				"status": "PENDING",
				"idempotency_key": f"snapshot::{frappe.generate_hash(length=12)}",
				"issuer_snapshot": '{"nit":"1234567-8"}',
			}
		).insert(ignore_permissions=True)

	def test_snapshot_fields_cannot_change_after_insert(self):
		operation = self._operation()
		operation.issuer_snapshot = '{"nit":"changed"}'
		with self.assertRaisesRegex(frappe.ValidationError, "inmutable"):
			operation.save(ignore_permissions=True)

	def test_event_is_append_only_and_snapshots_company_status(self):
		operation = self._operation()
		event_name = record_fel_event(operation.name, "CREATED", {"source": "test"})
		event = frappe.get_doc("GT FEL Operation Event", event_name)

		self.assertEqual(event.company, operation.company)
		self.assertEqual(event.status, "PENDING")
		with self.assertRaisesRegex(frappe.ValidationError, "no se pueden eliminar"):
			event.delete(ignore_permissions=True)
