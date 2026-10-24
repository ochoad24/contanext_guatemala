from dataclasses import dataclass
from decimal import Decimal

from contanext_guatemala.books.gl import apply_finance_book
from contanext_guatemala.books.journal import iter_journal_rows
from contanext_guatemala.books.ledger import iter_ledger_rows
from contanext_guatemala.books.trial_balance import trial_balance_dataset
from contanext_guatemala.books.types import BookScope, MovementTotals


@dataclass(frozen=True, slots=True)
class ReconciliationTotals:
	debit: Decimal
	credit: Decimal
	assets: Decimal
	liabilities: Decimal
	equity: Decimal
	income: Decimal
	expenses: Decimal

	@property
	def debit_credit_difference(self) -> Decimal:
		return self.debit - self.credit

	@property
	def accounting_equation_difference(self) -> Decimal:
		return self.assets + self.expenses - self.liabilities - self.equity - self.income

	@property
	def reconciled(self) -> bool:
		return self.debit_credit_difference == 0 and self.accounting_equation_difference == 0


def reconcile_gl(
	company: str, period_from: str, period_to: str, finance_book: str | None = None
) -> ReconciliationTotals:
	import frappe
	from frappe.query_builder.functions import Sum

	gle = frappe.qb.DocType("GL Entry")
	account = frappe.qb.DocType("Account")
	query = (
		frappe.qb.from_(gle)
		.join(account)
		.on((gle.account == account.name) & (gle.company == account.company))
		.select(
			account.root_type,
			Sum(gle.debit).as_("debit"),
			Sum(gle.credit).as_("credit"),
		)
		.where(gle.company == company)
		.where(gle.posting_date.between(period_from, period_to))
		.where(gle.is_cancelled == 0)
		.groupby(account.root_type)
	)
	rows = apply_finance_book(query, gle, finance_book).run(as_dict=True)
	debit = sum((_decimal(row.debit) for row in rows), Decimal(0))
	credit = sum((_decimal(row.credit) for row in rows), Decimal(0))
	balances = {row.root_type: _decimal(row.debit) - _decimal(row.credit) for row in rows}
	return ReconciliationTotals(
		debit=debit,
		credit=credit,
		assets=balances.get("Asset", Decimal(0)),
		liabilities=-balances.get("Liability", Decimal(0)),
		equity=-balances.get("Equity", Decimal(0)),
		income=-balances.get("Income", Decimal(0)),
		expenses=balances.get("Expense", Decimal(0)),
	)


def _decimal(value) -> Decimal:
	return Decimal(str(value or 0))


def reconcile_base_books(scope: BookScope, *, page_size: int = 5_000) -> dict:
	journal = _sum_rows(iter_journal_rows(scope, page_size=page_size), "debit", "credit")
	ledger = _sum_rows(
		(row for row in iter_ledger_rows(scope, page_size=page_size) if row["row_type"] == "MOVEMENT"),
		"debit",
		"credit",
	)
	trial = _sum_rows(
		trial_balance_dataset(scope, page_size=page_size).rows, "period_debit", "period_credit"
	)
	return {
		"journal": journal,
		"ledger": ledger,
		"trial_balance": trial,
		"debit_difference": max(journal.debit, ledger.debit, trial.debit)
		- min(journal.debit, ledger.debit, trial.debit),
		"credit_difference": max(journal.credit, ledger.credit, trial.credit)
		- min(journal.credit, ledger.credit, trial.credit),
		"reconciled": journal == ledger == trial and journal.debit == journal.credit,
	}


def _sum_rows(rows, debit_field: str, credit_field: str) -> MovementTotals:
	debit = Decimal(0)
	credit = Decimal(0)
	for row in rows:
		debit += _decimal(row[debit_field])
		credit += _decimal(row[credit_field])
	return MovementTotals(debit=debit, credit=credit)
