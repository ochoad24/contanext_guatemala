import json
import unittest
from datetime import datetime

from contanext_guatemala.books.operational_verification import (
	build_benchmark_report,
	measure_iterable,
	verify_folio_event_chain,
	verify_review_event_chain,
)
from contanext_guatemala.books.snapshots import (
	build_manifest,
	build_snapshot_parts,
	canonical_json,
	sha256_hex,
	verify_manifest,
)


class TestOperationalVerification(unittest.TestCase):
	def test_snapshot_manifest_verifier_rejects_tampering(self):
		manifest = build_manifest(build_snapshot_parts([{"value": 1}]), {"book": "JOURNAL"})
		self.assertTrue(verify_manifest(manifest))
		manifest["row_count"] = 2
		self.assertFalse(verify_manifest(manifest))

	def test_snapshot_manifest_rejects_invalid_part_hash(self):
		manifest = build_manifest(build_snapshot_parts([{"value": 1}]), {"book": "JOURNAL"})
		manifest["parts"][0]["sha256"] = "not-a-hash"
		unsigned = dict(manifest)
		unsigned.pop("root_sha256")
		manifest["root_sha256"] = sha256_hex(canonical_json(unsigned))
		self.assertFalse(verify_manifest(manifest))

	def test_measurement_has_count_memory_and_content_fingerprint(self):
		measurement = measure_iterable("TEST", ({"row": index} for index in range(3)))
		self.assertEqual(measurement["source_rows"], 3)
		self.assertEqual(measurement["result_rows"], 3)
		self.assertEqual(len(measurement["content_sha256"]), 64)
		self.assertGreaterEqual(measurement["peak_python_bytes"], 0)
		self.assertIsInstance(measurement["elapsed_seconds"], str)

	def test_benchmark_requires_explicit_approved_budget(self):
		measurement = {
			"label": "GL_JOURNAL", "source_rows": 100_000, "result_rows": 100_000,
			"elapsed_seconds": 4, "peak_python_bytes": 100, "content_sha256": "a" * 64,
		}
		without_budget = build_benchmark_report(scope={}, measurements=[measurement], environment={})
		self.assertEqual(without_budget["measurements"][0]["budget_status"], "NOT_APPROVED")
		with_budget = build_benchmark_report(
			scope={}, measurements=[measurement], environment={},
			approved_budgets={
				"GL_JOURNAL": {
					"max_seconds": 5,
					"max_peak_python_bytes": 200,
					"min_source_rows": 100_000,
				}
			},
		)
		self.assertEqual(with_budget["measurements"][0]["budget_status"], "PASSED")
		self.assertEqual(len(with_budget["report_sha256"]), 64)

	def test_review_event_chain_detects_changed_event(self):
		event = {
			"book_run": "RUN-1", "company": "ACME", "action": "APPROVED", "actor": "a@example.com",
			"event_at": datetime(2026, 1, 1), "comment": None, "emission_sha256": "a" * 64,
			"artifact_snapshot_json": "[]", "previous_event_sha256": "",
		}
		payload = {
			"book_run": event["book_run"], "company": event["company"], "action": event["action"],
			"actor": event["actor"], "event_at": str(event["event_at"]), "comment": None,
			"emission_sha256": event["emission_sha256"], "artifacts": [], "previous_event_sha256": "",
		}
		event["event_sha256"] = sha256_hex(canonical_json(payload))
		self.assertTrue(verify_review_event_chain([event]))
		event["action"] = "REJECTED"
		self.assertFalse(verify_review_event_chain([event]))

	def test_folio_event_chain_detects_broken_link(self):
		events = []
		previous = ""
		for action in ("RESERVED", "PRINT_CONFIRMED"):
			event = {
				"allocation": "ALLOC-1", "book_run": "RUN-1", "action": action,
				"actor": "a@example.com", "event_at": datetime(2026, 1, len(events) + 1),
				"idempotency_key": action.lower(), "failed_pages_json": "[]", "reason": None,
				"previous_event_sha256": previous,
			}
			payload = dict(event)
			payload.pop("failed_pages_json")
			payload["failed_pages"] = []
			payload["event_at"] = str(payload["event_at"])
			event["event_sha256"] = sha256_hex(canonical_json(payload))
			previous = event["event_sha256"]
			events.append(event)
		self.assertTrue(verify_folio_event_chain(events))
		events[1]["previous_event_sha256"] = "broken"
		self.assertFalse(verify_folio_event_chain(events))


if __name__ == "__main__":
	unittest.main()
