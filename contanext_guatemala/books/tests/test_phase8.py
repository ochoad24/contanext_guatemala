import io
import unittest
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

from contanext_guatemala.books.file_security import protect_book_file_before_save
from contanext_guatemala.books.rendering import build_prototype_html
from contanext_guatemala.books.requirements import (
	PackageEntry,
	build_requirement_manifest,
	build_requirement_zip,
	support_index_csv,
	verify_requirement_zip,
)


class TestSecurityAndRecoveryContracts(unittest.TestCase):
	def test_render_escapes_accounting_data_and_has_no_remote_resources(self):
		html, pages = build_prototype_html(
			book_title="Libro Diario",
			company='<script src="https://evil.invalid/x.js"></script>',
			period="2026-01-01 a 2026-01-31",
			tax_identity={"nit": "123<script>alert(1)</script>"},
			columns=("concept",),
			rows=({"concept": '<img src="https://evil.invalid/x" onerror="alert(1)">'},),
			emission_sha256="a" * 64,
		)
		self.assertEqual(pages, 1)
		self.assertNotIn("<script", html)
		self.assertNotIn("<img", html)
		self.assertNotIn('src="https://', html)
		self.assertIn("&lt;script", html)

	def test_support_index_neutralizes_spreadsheet_formulas(self):
		content = support_index_csv(
			[
				{
					"document_type": "DTE",
					"reference": "=HYPERLINK(\"https://evil.invalid\")",
					"description": "+CMD()",
				}
			]
		).decode("utf-8-sig")
		self.assertIn("'=HYPERLINK", content)
		self.assertIn("'+CMD()", content)

	def test_controlled_attachment_cannot_be_public(self):
		def throw(message):
			raise RuntimeError(message)

		fake_frappe = SimpleNamespace(throw=throw)
		file_doc = SimpleNamespace(
			attached_to_doctype="GT Accounting Book Run",
			attached_to_name="GT-RUN-1",
			is_private=0,
		)
		with patch.dict("sys.modules", {"frappe": fake_frappe}):
			with self.assertRaisesRegex(RuntimeError, "privados"):
				protect_book_file_before_save(file_doc)

	def test_requirement_zip_can_be_verified_independently(self):
		entries = [PackageEntry("02-libro-diario/diario.csv", b"a,b\n1,2\n")]
		manifest = build_requirement_manifest(package={"company": "ACME"}, entries=entries)
		content = build_requirement_zip("REQ-1", entries, manifest)
		self.assertTrue(verify_requirement_zip(content))

	def test_requirement_zip_verifier_rejects_tampering_and_extra_files(self):
		entries = [PackageEntry("02-libro-diario/diario.csv", b"original")]
		manifest = build_requirement_manifest(package={"company": "ACME"}, entries=entries)
		content = build_requirement_zip("REQ-1", entries, manifest)
		with zipfile.ZipFile(io.BytesIO(content)) as source:
			files = {name: source.read(name) for name in source.namelist()}

		for name in files:
			if name.endswith("diario.csv"):
				files[name] = b"alterado"
		output = io.BytesIO()
		with zipfile.ZipFile(output, "w") as archive:
			for name, payload in files.items():
				archive.writestr(name, payload)
			archive.writestr("REQ-1/no-manifestado.txt", b"extra")
		self.assertFalse(verify_requirement_zip(output.getvalue()))

	def test_requirement_zip_verifier_rejects_non_object_manifest(self):
		output = io.BytesIO()
		with zipfile.ZipFile(output, "w") as archive:
			archive.writestr("REQ-1/00-manifiesto.json", b"[]")
		self.assertFalse(verify_requirement_zip(output.getvalue()))


if __name__ == "__main__":
	unittest.main()
