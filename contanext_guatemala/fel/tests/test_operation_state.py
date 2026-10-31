import json
from pathlib import Path

import frappe
from frappe.tests.utils import FrappeTestCase


DEFINITION = Path(__file__).parents[2] / "contanext_guatemala" / "doctype" / "fel_operation" / "fel_operation.json"


class TestFELOperationState(FrappeTestCase):
	def _operation(self, status="PENDING"):
		company = frappe.get_all("Company", pluck="name", limit=1)[0]
		return frappe.get_doc(
			{
				"doctype": "FEL Operation",
				"company": company,
				"document_type": "FACT",
				"source_doctype": "Company",
				"source_name": company,
				"operation": "CERTIFY",
				"status": status,
				"idempotency_key": f"state::{frappe.generate_hash(length=12)}",
			}
		)

	def test_metadata_contains_all_states_types_and_operations(self):
		definition = json.loads(DEFINITION.read_text())
		fields = {field["fieldname"]: field for field in definition["fields"]}

		self.assertIn("REJECTED", fields["status"]["options"])
		self.assertIn("RECONCILIATION_REQUIRED", fields["status"]["options"])
		self.assertIn("FESP", fields["document_type"]["options"])
		self.assertIn("RECONCILE", fields["operation"]["options"])
		self.assertEqual(fields["idempotency_key"]["unique"], 1)

	def test_new_operation_must_start_pending(self):
		with self.assertRaisesRegex(frappe.ValidationError, "iniciar en PENDING"):
			self._operation("PROCESSING").insert(ignore_permissions=True)

	def test_valid_and_invalid_transitions_are_enforced(self):
		operation = self._operation().insert(ignore_permissions=True)
		operation.status = "PROCESSING"
		operation.save(ignore_permissions=True)
		operation.status = "CERTIFIED"
		operation.save(ignore_permissions=True)

		operation.status = "PROCESSING"
		with self.assertRaisesRegex(frappe.ValidationError, "no está permitida"):
			operation.save(ignore_permissions=True)

	def test_cancel_and_reconcile_require_original_operation(self):
		operation = self._operation()
		operation.operation = "CANCEL"
		with self.assertRaisesRegex(frappe.ValidationError, "operación original"):
			operation.insert(ignore_permissions=True)
