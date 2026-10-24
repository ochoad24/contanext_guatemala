import unittest
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from contanext_guatemala.books.exports import csv_bytes
from contanext_guatemala.books.journal import iter_journal_rows
from contanext_guatemala.books.ledger import iter_ledger_rows
from contanext_guatemala.books.trial_balance import trial_balance_dataset
from contanext_guatemala.books.types import BookScope


SCOPE = BookScope(
	company="Empresa GT",
	period_from=date(2026, 1, 1),
	period_to=date(2026, 1, 31),
	fiscal_year="2026",
)


def gl(name, account, number, debit="0", credit="0", posting_date=date(2026, 1, 5)):
	return SimpleNamespace(
		name=name,
		posting_date=posting_date,
		voucher_type="Journal Entry",
		voucher_no="JV-1",
		account=account,
		account_number=number,
		account_name=account,
		root_type="Asset" if debit != "0" else "Liability",
		remarks="Prueba",
		party_type=None,
		party=None,
		cost_center=None,
		project=None,
		against=None,
		is_opening="No",
		debit=Decimal(debit),
		credit=Decimal(credit),
	)


class TestPhase2Books(unittest.TestCase):
	def test_journal_assigns_stable_entry_and_line_sequences(self):
		rows = [gl("GLE-1", "Caja", "1", debit="10"), gl("GLE-2", "Capital", "2", credit="10")]
		with patch("contanext_guatemala.books.journal.iter_gl_entries", return_value=iter(rows)):
			result = list(iter_journal_rows(SCOPE))
		self.assertEqual([row["entry_sequence"] for row in result], [1, 1])
		self.assertEqual([row["line_sequence"] for row in result], [1, 2])
		self.assertEqual(sum((row["debit"] for row in result), Decimal(0)), Decimal("10"))

	def test_ledger_carries_opening_and_running_balance(self):
		opening = [gl("GLE-0", "Caja", "1", debit="5", posting_date=date(2025, 12, 31))]
		period = [gl("GLE-1", "Caja", "1", debit="10")]

		def source(_scope, *, before=None, **_kwargs):
			return iter(opening if before else period)

		with patch("contanext_guatemala.books.ledger.iter_gl_entries", side_effect=source):
			result = list(iter_ledger_rows(SCOPE))
		self.assertEqual([row["row_type"] for row in result], ["OPENING", "MOVEMENT", "CLOSING"])
		self.assertEqual(result[0]["running_balance"], Decimal("5"))
		self.assertEqual(result[-1]["running_balance"], Decimal("15"))

	def test_trial_balance_exposes_opening_movements_and_closing(self):
		opening = [gl("GLE-0", "Caja", "1", debit="5", posting_date=date(2025, 12, 31))]
		period = [gl("GLE-1", "Caja", "1", debit="10")]

		def source(_scope, *, before=None, **_kwargs):
			return iter(opening if before else period)

		with patch("contanext_guatemala.books.trial_balance.iter_gl_entries", side_effect=source):
			result = list(trial_balance_dataset(SCOPE).rows)
		self.assertEqual(result[0]["opening_debit"], Decimal("5"))
		self.assertEqual(result[0]["period_debit"], Decimal("10"))
		self.assertEqual(result[0]["closing_debit"], Decimal("15"))

	def test_csv_has_fixed_columns_utf8_bom_and_neutralizes_formulas(self):
		content = csv_bytes(("account", "debit"), [{"account": "=CMD()", "debit": "10"}])
		self.assertTrue(content.startswith(b"\xef\xbb\xbf"))
		self.assertIn(b"'=CMD()", content)


if __name__ == "__main__":
	unittest.main()
