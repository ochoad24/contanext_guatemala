import unittest

from contanext_guatemala.books.folios import plan_range, required_folios, validate_failed_pages
from contanext_guatemala.books.manifests import build_seal_manifest, verify_seal_bundle, verify_seal_manifest
from contanext_guatemala.books.snapshots import sha256_hex


class TestPhaseFiveContracts(unittest.TestCase):
	def test_simplex_allocates_one_folio_per_pdf_page(self):
		planned = plan_range(101, 3)
		self.assertEqual((planned.first, planned.last, planned.count), (101, 103, 3))

	def test_duplex_fails_closed_while_legal_gate_is_open(self):
		with self.assertRaises(ValueError):
			required_folios(3, "DUPLEX")

	def test_failed_pages_are_unique_ordered_and_bounded(self):
		self.assertEqual(validate_failed_pages(5, [3, 2, 3]), (2, 3))
		with self.assertRaises(ValueError):
			validate_failed_pages(5, [6])

	def test_manifest_hash_has_no_circular_reference(self):
		manifest = build_seal_manifest(
			book_run="GT-BK-1", emission_sha256="a" * 64, pdf_sha256="b" * 64,
			page_count=2, allocation={"first_folio": 1, "last_folio": 2},
			artifacts=[{"type": "SEALED_PDF", "sha256": "b" * 64}],
			renderer={"engine": "Chromium", "version": "test"},
		)
		self.assertTrue(verify_seal_manifest(manifest))
		manifest["page_count"] = 3
		self.assertFalse(verify_seal_manifest(manifest))

	def test_bundle_verifier_recalculates_artifact_hashes(self):
		pdf = b"%PDF-prototype"
		manifest = build_seal_manifest(
			book_run="GT-BK-1", emission_sha256="a" * 64, pdf_sha256=sha256_hex(pdf),
			page_count=1, allocation={"first_folio": 1, "last_folio": 1},
			artifacts=[{"type": "SEALED_PDF", "file_url": "/private/test.pdf", "sha256": sha256_hex(pdf)}],
			renderer={"engine": "Chromium", "version": "test"},
		)
		self.assertTrue(verify_seal_bundle(manifest, {"/private/test.pdf": pdf}))
		self.assertFalse(verify_seal_bundle(manifest, {"/private/test.pdf": b"changed"}))


if __name__ == "__main__":
	unittest.main()
