import unittest

from contanext_guatemala.books.types import CheckResult


class TestCheckResult(unittest.TestCase):
	def test_only_failed_error_or_blocker_stops_preflight(self):
		self.assertTrue(CheckResult("A", "ACCOUNTING", "BLOCKER", "FAIL", "").blocks)
		self.assertTrue(CheckResult("B", "ACCOUNTING", "ERROR", "FAIL", "").blocks)
		self.assertFalse(CheckResult("C", "ACCOUNTING", "WARNING", "FAIL", "").blocks)
		self.assertFalse(CheckResult("D", "ACCOUNTING", "BLOCKER", "PASS", "").blocks)


if __name__ == "__main__":
	unittest.main()
