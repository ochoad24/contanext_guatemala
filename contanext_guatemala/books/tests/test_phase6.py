import io
import unittest
import zipfile

from contanext_guatemala.books.monitoring import _contains_blocking_difference, change_fingerprint
from contanext_guatemala.books.requirements import (
	PackageEntry,
	build_requirement_manifest,
	build_requirement_zip,
	missing_requested_artifacts,
	safe_component,
	support_index_csv,
	validate_entry_path,
)


class TestPhaseSixContracts(unittest.TestCase):
	def test_package_is_deterministic_and_manifested(self):
		entries = [PackageEntry("02-libro-diario/diario.csv", b"a,b\n1,2\n")]
		manifest = build_requirement_manifest(package={"company": "ACME"}, entries=entries)
		first = build_requirement_zip("REQ-1", entries, manifest)
		second = build_requirement_zip("REQ-1", entries, manifest)
		self.assertEqual(first, second)
		with zipfile.ZipFile(io.BytesIO(first)) as archive:
			self.assertEqual(
				archive.namelist(),
				["REQ-1/00-manifiesto.json", "REQ-1/02-libro-diario/diario.csv"],
			)

	def test_zip_paths_cannot_escape_package(self):
		with self.assertRaises(ValueError):
			validate_entry_path("../../otra-empresa.csv")
		self.assertEqual(safe_component("REQ / 2026"), "REQ-2026")

	def test_support_index_does_not_claim_files_are_included(self):
		content = support_index_csv([{"document_type": "DTE", "reference": "F-1"}]).decode("utf-8-sig")
		self.assertIn("F-1", content)
		self.assertTrue(content.rstrip().endswith(",NO"))

	def test_requested_artifacts_must_all_exist(self):
		self.assertEqual(
			missing_requested_artifacts(
				{"SEALED_PDF", "CSV", "SEAL_MANIFEST"},
				{"SEALED_PDF", "CSV"},
			),
			{"SEAL_MANIFEST"},
		)

	def test_change_fingerprint_is_stable_and_run_scoped(self):
		signals = [{"category": "POST_CUTOFF_GL", "count": 1}]
		self.assertEqual(change_fingerprint("RUN-1", signals), change_fingerprint("RUN-1", signals))
		self.assertNotEqual(change_fingerprint("RUN-1", signals), change_fingerprint("RUN-2", signals))

	def test_nested_reconciliation_difference_is_detected(self):
		self.assertTrue(_contains_blocking_difference({"inventory": {"reconciled": False}}))
		self.assertFalse(_contains_blocking_difference({"journal": {"reconciled": True}}))


if __name__ == "__main__":
	unittest.main()
