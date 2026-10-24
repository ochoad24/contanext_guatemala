import gzip
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from contanext_guatemala.books.snapshots import (
	build_manifest,
	build_snapshot_parts,
	canonical_json,
	emission_sha256,
)


class TestSnapshots(unittest.TestCase):
	def test_canonical_json_is_stable_and_rejects_float(self):
		left = {"amount": Decimal("10.5000"), "date": datetime(2026, 1, 1, tzinfo=timezone.utc)}
		right = {"date": datetime(2026, 1, 1, tzinfo=timezone.utc), "amount": Decimal("10.5")}
		self.assertEqual(canonical_json(left), canonical_json(right))
		with self.assertRaises(TypeError):
			canonical_json({"amount": 10.5})

	def test_partitioned_snapshot_is_reproducible(self):
		rows = [{"id": index, "debit": Decimal("1.00")} for index in range(3)]
		first = build_snapshot_parts(rows, max_rows=2)
		second = build_snapshot_parts(rows, max_rows=2)
		self.assertEqual([part.sha256 for part in first], [part.sha256 for part in second])
		self.assertEqual([part.row_count for part in first], [2, 1])
		self.assertEqual(gzip.decompress(first[0].content).count(b"\n"), 2)

		manifest = build_manifest(first, {"company": "Empresa GT", "currency": "GTQ"})
		self.assertEqual(manifest["row_count"], 3)
		self.assertEqual(
			emission_sha256(manifest, {"book_type": "JOURNAL"}),
			emission_sha256(manifest, {"book_type": "JOURNAL"}),
		)


if __name__ == "__main__":
	unittest.main()
