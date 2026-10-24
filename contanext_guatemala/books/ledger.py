from collections.abc import Iterator
from decimal import Decimal

from contanext_guatemala.books.gl import decimal_value, iter_gl_entries
from contanext_guatemala.books.types import BookDataset, BookScope


LEDGER_COLUMNS = (
	"account_number",
	"account",
	"account_name",
	"row_type",
	"posting_date",
	"voucher_type",
	"voucher_no",
	"concept",
	"debit",
	"credit",
	"running_balance",
	"source_gl_entry",
)


def ledger_dataset(scope: BookScope, *, page_size: int = 5_000) -> BookDataset:
	return BookDataset(columns=LEDGER_COLUMNS, rows=iter_ledger_rows(scope, page_size=page_size))


def iter_ledger_rows(scope: BookScope, *, page_size: int = 5_000) -> Iterator[dict]:
	openings = _opening_balances(scope, page_size=page_size)
	current_account = None
	balance = Decimal(0)
	account_meta = None
	for source in iter_gl_entries(scope, order="ledger", page_size=page_size):
		if source.account != current_account:
			if current_account is not None:
				yield _boundary_row(account_meta, "CLOSING", scope.period_to, balance)
			current_account = source.account
			account_meta = source
			opening = openings.pop(source.account, None)
			balance = opening["balance"] if opening else Decimal(0)
			yield _boundary_row(source, "OPENING", scope.period_from, balance)
		debit = decimal_value(source.debit)
		credit = decimal_value(source.credit)
		balance += debit - credit
		yield {
			"account_number": source.account_number or "",
			"account": source.account,
			"account_name": source.account_name,
			"row_type": "MOVEMENT",
			"posting_date": source.posting_date,
			"voucher_type": source.voucher_type,
			"voucher_no": source.voucher_no,
			"concept": source.remarks or "",
			"debit": debit,
			"credit": credit,
			"running_balance": balance,
			"source_gl_entry": source.name,
		}
	if current_account is not None:
		yield _boundary_row(account_meta, "CLOSING", scope.period_to, balance)
	for account in sorted(openings, key=lambda name: openings[name]["sort_key"]):
		meta = openings[account]["meta"]
		balance = openings[account]["balance"]
		yield _boundary_row(meta, "OPENING", scope.period_from, balance)
		yield _boundary_row(meta, "CLOSING", scope.period_to, balance)


def _opening_balances(scope: BookScope, *, page_size: int) -> dict:
	balances: dict = {}
	for source in iter_gl_entries(scope, before=scope.period_from, order="ledger", page_size=page_size):
		item = balances.setdefault(
			source.account,
			{
				"balance": Decimal(0),
				"meta": source,
				"sort_key": (source.account_number or "", source.account),
			},
		)
		item["balance"] += decimal_value(source.debit) - decimal_value(source.credit)
	return balances


def _boundary_row(source, row_type: str, posting_date, balance: Decimal) -> dict:
	return {
		"account_number": source.account_number or "",
		"account": source.account,
		"account_name": source.account_name,
		"row_type": row_type,
		"posting_date": posting_date,
		"voucher_type": "",
		"voucher_no": "",
		"concept": "Saldo inicial" if row_type == "OPENING" else "Saldo final",
		"debit": Decimal(0),
		"credit": Decimal(0),
		"running_balance": balance,
		"source_gl_entry": "",
	}
