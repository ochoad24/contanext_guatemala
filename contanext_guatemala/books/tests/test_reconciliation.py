import unittest
from decimal import Decimal

from contanext_guatemala.books.reconciliation import ReconciliationTotals


class TestReconciliation(unittest.TestCase):
	def test_balanced_accounting_equation(self):
		totals = ReconciliationTotals(
			debit=Decimal("150"),
			credit=Decimal("150"),
			assets=Decimal("100"),
			liabilities=Decimal("40"),
			equity=Decimal("50"),
			income=Decimal("60"),
			expenses=Decimal("50"),
		)
		self.assertTrue(totals.reconciled)

	def test_difference_is_explicit(self):
		totals = ReconciliationTotals(
			debit=Decimal("10"),
			credit=Decimal("9"),
			assets=Decimal("10"),
			liabilities=Decimal("9"),
			equity=Decimal("0"),
			income=Decimal("0"),
			expenses=Decimal("0"),
		)
		self.assertEqual(totals.debit_credit_difference, Decimal("1"))
		self.assertEqual(totals.accounting_equation_difference, Decimal("1"))
		self.assertFalse(totals.reconciled)


if __name__ == "__main__":
	unittest.main()
