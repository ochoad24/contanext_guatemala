from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from contanext_guatemala.books.gl import decimal_value, iter_gl_entries
from contanext_guatemala.books.types import BookDataset, BookScope


FINANCIAL_STATEMENT_COLUMNS = (
	"statement",
	"row_type",
	"section",
	"account_number",
	"account",
	"account_name",
	"amount",
)


@dataclass(frozen=True, slots=True)
class FinancialStatementTotals:
	assets: Decimal
	liabilities: Decimal
	equity_before_result: Decimal
	income: Decimal
	expenses: Decimal

	@property
	def period_result(self) -> Decimal:
		return self.income - self.expenses

	@property
	def balance_difference(self) -> Decimal:
		return self.assets - self.liabilities - self.equity_before_result - self.period_result

	@property
	def reconciled(self) -> bool:
		return self.balance_difference == 0


def balance_sheet_dataset(scope: BookScope, *, page_size: int = 5_000) -> BookDataset:
	balances = _account_balances(_entries_through_cutoff(scope, page_size=page_size))
	period = _account_balances(iter_gl_entries(scope, order="ledger", page_size=page_size))
	period_result = _root_total(period, "Income") - _root_total(period, "Expense")
	rows: list[dict] = []
	for root_type, section in (("Asset", "ACTIVO"), ("Liability", "PASIVO"), ("Equity", "PATRIMONIO")):
		for item in _items_for_root(balances, root_type):
			rows.append(_statement_row("BALANCE_GENERAL", "ACCOUNT", section, item, _natural_amount(item)))
		rows.append(_total_row("BALANCE_GENERAL", section, _root_total(balances, root_type)))
	rows.append(
		{
			"statement": "BALANCE_GENERAL",
			"row_type": "CURRENT_RESULT",
			"section": "PATRIMONIO",
			"account_number": "",
			"account": "",
			"account_name": "Resultado del período",
			"amount": period_result,
		}
	)
	rows.append(
		_total_row(
			"BALANCE_GENERAL",
			"PASIVO_Y_PATRIMONIO",
			_root_total(balances, "Liability") + _root_total(balances, "Equity") + period_result,
		)
	)
	return BookDataset(columns=FINANCIAL_STATEMENT_COLUMNS, rows=iter(rows))


def income_statement_dataset(scope: BookScope, *, page_size: int = 5_000) -> BookDataset:
	balances = _account_balances(iter_gl_entries(scope, order="ledger", page_size=page_size))
	rows: list[dict] = []
	for root_type, section in (("Income", "INGRESOS"), ("Expense", "GASTOS_Y_COSTOS")):
		for item in _items_for_root(balances, root_type):
			rows.append(_statement_row("ESTADO_RESULTADOS", "ACCOUNT", section, item, _natural_amount(item)))
		rows.append(_total_row("ESTADO_RESULTADOS", section, _root_total(balances, root_type)))
	rows.append(
		_total_row(
			"ESTADO_RESULTADOS",
			"RESULTADO_DEL_PERIODO",
			_root_total(balances, "Income") - _root_total(balances, "Expense"),
		)
	)
	return BookDataset(columns=FINANCIAL_STATEMENT_COLUMNS, rows=iter(rows))


def financial_statements_dataset(scope: BookScope, *, page_size: int = 5_000) -> BookDataset:
	"""Build the ordered logical package. PDF composition belongs to phase 5."""
	cover = {
		"statement": "CARATULA",
		"row_type": "COVER",
		"section": "LIBRO_ESTADOS_FINANCIEROS",
		"account_number": "",
		"account": "",
		"account_name": scope.company,
		"amount": None,
	}
	rows = [cover]
	rows.extend(balance_sheet_dataset(scope, page_size=page_size).rows)
	rows.extend(income_statement_dataset(scope, page_size=page_size).rows)
	return BookDataset(columns=FINANCIAL_STATEMENT_COLUMNS, rows=iter(rows))


def reconcile_financial_statements(scope: BookScope, *, page_size: int = 5_000) -> FinancialStatementTotals:
	cutoff = _account_balances(_entries_through_cutoff(scope, page_size=page_size))
	period = _account_balances(iter_gl_entries(scope, order="ledger", page_size=page_size))
	return FinancialStatementTotals(
		assets=_root_total(cutoff, "Asset"),
		liabilities=_root_total(cutoff, "Liability"),
		equity_before_result=_root_total(cutoff, "Equity"),
		income=_root_total(period, "Income"),
		expenses=_root_total(period, "Expense"),
	)


def _entries_through_cutoff(scope: BookScope, *, page_size: int) -> Iterable[Mapping]:
	yield from iter_gl_entries(scope, before=scope.period_from, order="ledger", page_size=page_size)
	yield from iter_gl_entries(scope, order="ledger", page_size=page_size)


def _account_balances(entries: Iterable[Mapping]) -> dict[str, dict]:
	accounts: dict[str, dict] = {}
	for source in entries:
		item = accounts.setdefault(
			source.account,
			{
				"account_number": source.account_number or "",
				"account": source.account,
				"account_name": source.account_name,
				"root_type": source.root_type,
				"debit": Decimal(0),
				"credit": Decimal(0),
			},
		)
		item["debit"] += decimal_value(source.debit)
		item["credit"] += decimal_value(source.credit)
	return accounts


def _natural_amount(item: Mapping) -> Decimal:
	if item["root_type"] in {"Liability", "Equity", "Income"}:
		return item["credit"] - item["debit"]
	return item["debit"] - item["credit"]


def _items_for_root(accounts: Mapping[str, dict], root_type: str) -> list[dict]:
	return sorted(
		(item for item in accounts.values() if item["root_type"] == root_type),
		key=lambda item: (item["account_number"], item["account"]),
	)


def _root_total(accounts: Mapping[str, dict], root_type: str) -> Decimal:
	return sum((_natural_amount(item) for item in _items_for_root(accounts, root_type)), Decimal(0))


def _statement_row(statement: str, row_type: str, section: str, item: Mapping, amount) -> dict:
	return {
		"statement": statement,
		"row_type": row_type,
		"section": section,
		"account_number": item["account_number"],
		"account": item["account"],
		"account_name": item["account_name"],
		"amount": amount,
	}


def _total_row(statement: str, section: str, amount: Decimal) -> dict:
	return {
		"statement": statement,
		"row_type": "TOTAL",
		"section": section,
		"account_number": "",
		"account": "",
		"account_name": f"Total {section.lower().replace('_', ' ')}",
		"amount": amount,
	}
