from collections.abc import Iterator
from datetime import date
from decimal import Decimal

from contanext_guatemala.books.types import BookScope


def decimal_value(value) -> Decimal:
	return Decimal(str(value or 0))


def iter_gl_entries(
	scope: BookScope,
	*,
	before: date | None = None,
	order: str = "journal",
	page_size: int = 5_000,
) -> Iterator[dict]:
	"""Read GL rows in bounded pages with a total, versioned order."""
	import frappe

	if page_size < 1:
		raise ValueError("page_size debe ser positivo.")
	gle = frappe.qb.DocType("GL Entry")
	account = frappe.qb.DocType("Account")
	query = (
		frappe.qb.from_(gle)
		.join(account)
		.on((gle.account == account.name) & (gle.company == account.company))
		.select(
			gle.name,
			gle.posting_date,
			gle.voucher_type,
			gle.voucher_no,
			gle.account,
			account.account_number,
			account.account_name,
			account.root_type,
			gle.remarks,
			gle.party_type,
			gle.party,
			gle.cost_center,
			gle.project,
			gle.against,
			gle.is_opening,
			gle.debit,
			gle.credit,
		)
		.where(gle.company == scope.company)
		.where(gle.is_cancelled == 0)
	)
	if before is not None:
		query = query.where(gle.posting_date < before)
	else:
		query = query.where(gle.posting_date.between(scope.period_from, scope.period_to))
	query = apply_finance_book(query, gle, scope.finance_book)
	if order == "ledger":
		query = query.orderby(
			account.account_number, gle.account, gle.posting_date, gle.voucher_type, gle.voucher_no, gle.name
		)
	elif order == "journal":
		query = query.orderby(
			gle.posting_date, gle.voucher_type, gle.voucher_no, account.account_number, gle.account, gle.name
		)
	else:
		raise ValueError(f"Orden GL desconocido: {order}")

	offset = 0
	while True:
		page = query.limit(page_size).offset(offset).run(as_dict=True)
		if not page:
			break
		for row in page:
			yield row
		if len(page) < page_size:
			break
		offset += page_size


def account_catalog(scope: BookScope) -> list[dict]:
	import frappe

	account = frappe.qb.DocType("Account")
	rows = (
		frappe.qb.from_(account)
		.select(
			account.name,
			account.account_number,
			account.account_name,
			account.parent_account,
			account.root_type,
			account.report_type,
			account.is_group,
			account.lft,
			account.rgt,
		)
		.where(account.company == scope.company)
		.orderby(account.lft, account.name)
	).run(as_dict=True)
	return [dict(row) for row in rows]


def apply_finance_book(query, gle, finance_book: str | None):
	"""Apply the closed finance-book scope used by every books query.

	ERPNext treats blank finance-book rows as common entries.  A selected book
	therefore includes that book plus common entries; an unselected book includes
	only common entries.  Preflight and reconciliation must use this exact helper
	so they cannot validate a wider dataset than the generated artifact.
	"""
	blank = (gle.finance_book == "") | gle.finance_book.isnull()
	return query.where(blank | (gle.finance_book == finance_book)) if finance_book else query.where(blank)
