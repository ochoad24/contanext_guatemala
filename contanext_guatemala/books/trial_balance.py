from decimal import Decimal

from contanext_guatemala.books.gl import decimal_value, iter_gl_entries
from contanext_guatemala.books.types import BookDataset, BookScope


TRIAL_BALANCE_COLUMNS = (
	"account_number",
	"account",
	"account_name",
	"root_type",
	"opening_debit",
	"opening_credit",
	"period_debit",
	"period_credit",
	"closing_debit",
	"closing_credit",
)


def trial_balance_dataset(scope: BookScope, *, page_size: int = 5_000) -> BookDataset:
	return BookDataset(columns=TRIAL_BALANCE_COLUMNS, rows=iter(_build_rows(scope, page_size=page_size)))


def _build_rows(scope: BookScope, *, page_size: int) -> list[dict]:
	accounts: dict[str, dict] = {}
	for source in iter_gl_entries(scope, before=scope.period_from, order="ledger", page_size=page_size):
		item = _account_item(accounts, source)
		item["opening"] += decimal_value(source.debit) - decimal_value(source.credit)
	for source in iter_gl_entries(scope, order="ledger", page_size=page_size):
		item = _account_item(accounts, source)
		item["period_debit"] += decimal_value(source.debit)
		item["period_credit"] += decimal_value(source.credit)

	rows = []
	for item in sorted(accounts.values(), key=lambda row: row["sort_key"]):
		closing = item["opening"] + item["period_debit"] - item["period_credit"]
		rows.append(
			{
				"account_number": item["account_number"],
				"account": item["account"],
				"account_name": item["account_name"],
				"root_type": item["root_type"],
				"opening_debit": max(item["opening"], Decimal(0)),
				"opening_credit": max(-item["opening"], Decimal(0)),
				"period_debit": item["period_debit"],
				"period_credit": item["period_credit"],
				"closing_debit": max(closing, Decimal(0)),
				"closing_credit": max(-closing, Decimal(0)),
			}
		)
	return rows


def _account_item(accounts: dict, source) -> dict:
	return accounts.setdefault(
		source.account,
		{
			"sort_key": (source.account_number or "", source.account),
			"account_number": source.account_number or "",
			"account": source.account,
			"account_name": source.account_name,
			"root_type": source.root_type,
			"opening": Decimal(0),
			"period_debit": Decimal(0),
			"period_credit": Decimal(0),
		},
	)
