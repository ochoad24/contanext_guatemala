import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from contanext_guatemala.books.financial_statements import (
	balance_sheet_dataset,
	financial_statements_dataset,
	income_statement_dataset,
	reconcile_financial_statements,
)
from contanext_guatemala.books.pdf_validation import validate_pdf
from contanext_guatemala.books.types import BookScope


SCOPE = BookScope("Empresa GT", date(2026, 1, 1), date(2026, 12, 31), "2026")


def gl(account, number, root_type, debit="0", credit="0"):
	return SimpleNamespace(
		account=account,
		account_number=number,
		account_name=account,
		root_type=root_type,
		debit=Decimal(debit),
		credit=Decimal(credit),
	)


OPENING = [gl("Caja", "1", "Asset", debit="100"), gl("Capital", "3", "Equity", credit="100")]
PERIOD = [
	gl("Caja", "1", "Asset", debit="40"),
	gl("Ventas", "4", "Income", credit="40"),
	gl("Gastos", "5", "Expense", debit="10"),
	gl("Caja", "1", "Asset", credit="10"),
]


def entries(_scope, *, before=None, **_kwargs):
	return iter(OPENING if before else PERIOD)


class TestFinancialStatements(unittest.TestCase):
	@patch("contanext_guatemala.books.financial_statements.iter_gl_entries", side_effect=entries)
	def test_balance_sheet_includes_reconciled_period_result(self, _source):
		rows = list(balance_sheet_dataset(SCOPE).rows)
		current_result = next(row for row in rows if row["row_type"] == "CURRENT_RESULT")
		self.assertEqual(current_result["amount"], Decimal("30"))
		self.assertEqual(rows[-1]["amount"], Decimal("130"))

	@patch("contanext_guatemala.books.financial_statements.iter_gl_entries", side_effect=entries)
	def test_income_statement_and_balance_reconcile(self, _source):
		rows = list(income_statement_dataset(SCOPE).rows)
		self.assertEqual(rows[-1]["section"], "RESULTADO_DEL_PERIODO")
		self.assertEqual(rows[-1]["amount"], Decimal("30"))
		totals = reconcile_financial_statements(SCOPE)
		self.assertTrue(totals.reconciled)
		self.assertEqual(totals.balance_difference, 0)

	@patch("contanext_guatemala.books.financial_statements.iter_gl_entries", side_effect=entries)
	def test_orchestrator_orders_cover_balance_and_results(self, _source):
		rows = list(financial_statements_dataset(SCOPE).rows)
		self.assertEqual(rows[0]["statement"], "CARATULA")
		statements = [row["statement"] for row in rows]
		self.assertLess(statements.index("BALANCE_GENERAL"), statements.index("ESTADO_RESULTADOS"))

	def test_pdf_validation_rejects_non_pdf_and_active_content(self):
		with self.assertRaises(ValueError):
			validate_pdf(b"not a pdf")
		with self.assertRaises(ValueError):
			validate_pdf(b"%PDF-1.7\n/JavaScript")


if __name__ == "__main__":
	unittest.main()
