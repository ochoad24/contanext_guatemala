from unittest import TestCase
from unittest.mock import patch

from contanext_guatemala.fel.artifacts import canonical_json, save_private_artifact, sha256_hex, snapshot_hash


class FakeFile:
	def __init__(self, values):
		self.values = values

	def insert(self, ignore_permissions=False):
		self.ignore_permissions = ignore_permissions
		self.name = "FILE-1"
		return self


class TestFELArtifacts(TestCase):
	def test_snapshot_hash_is_deterministic_and_unicode_safe(self):
		left = {"name": "José & Cía.", "amount": "10.00"}
		right = {"amount": "10.00", "name": "José & Cía."}
		self.assertEqual(snapshot_hash(left), snapshot_hash(right))
		self.assertIn("José".encode(), canonical_json(left))

	def test_pdf_requires_signature_and_all_files_are_private(self):
		with self.assertRaisesRegex(ValueError, "firma PDF"):
			save_private_artifact(
				operation_name="FEL-OP-1", filename="dte.pdf", content=b"not-pdf", artifact_type="PDF"
			)

		with patch("contanext_guatemala.fel.artifacts.frappe.get_doc", side_effect=FakeFile) as get_doc:
			file_doc, digest = save_private_artifact(
				operation_name="FEL-OP-1",
				filename="dte.pdf",
				content=b"%PDF-1.7\ncontent",
				artifact_type="PDF",
			)

		values = get_doc.call_args.args[0]
		self.assertEqual(values["is_private"], 1)
		self.assertEqual(values["attached_to_doctype"], "FEL Operation")
		self.assertTrue(file_doc.ignore_permissions)
		self.assertEqual(digest, sha256_hex(b"%PDF-1.7\ncontent"))
