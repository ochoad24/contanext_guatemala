from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

from contanext_guatemala.books.gl import apply_finance_book, decimal_value
from contanext_guatemala.books.types import BookDataset, BookScope


INVENTORY_COLUMNS = (
	"row_type",
	"item_code",
	"item_name",
	"item_group",
	"warehouse",
	"uom",
	"book_quantity",
	"counted_quantity",
	"quantity_difference",
	"valuation_rate",
	"stock_value",
	"inventory_account",
	"gl_value",
	"value_difference",
	"cause",
)


@dataclass(frozen=True, slots=True)
class InventoryReconciliation:
	rows: tuple[dict, ...]
	stock_value: Decimal
	gl_value: Decimal
	unmapped: int
	ambiguous: int
	negative: int
	physical_differences: int

	@property
	def value_difference(self) -> Decimal:
		return self.stock_value - self.gl_value

	@property
	def reconciled(self) -> bool:
		return not any(
		(self.unmapped, self.ambiguous, self.negative, self.physical_differences, self.value_difference)
		)


def collapse_sle_rows(rows: Iterable[Mapping]) -> Iterator[dict]:
	"""Yield one closing balance per sorted item/warehouse using constant working memory."""
	current_key = None
	current = None
	for row in rows:
		key = (row.item_code, row.warehouse)
		if current_key is not None and key != current_key:
			yield _inventory_balance(current)
		current_key = key
		current = row
	if current is not None:
		yield _inventory_balance(current)


def iter_inventory_balances(scope: BookScope, *, page_size: int = 5_000) -> Iterator[dict]:
	if page_size < 1:
		raise ValueError("page_size debe ser positivo.")
	yield from collapse_sle_rows(iter_sle_rows(scope, page_size=page_size))


def iter_sle_rows(scope: BookScope, *, page_size: int = 5_000) -> Iterator[Mapping]:
	"""Read SLE source rows with keyset pagination and a total stable order."""
	import frappe
	if page_size < 1:
		raise ValueError("page_size debe ser positivo.")

	sle = frappe.qb.DocType("Stock Ledger Entry")
	item = frappe.qb.DocType("Item")
	cursor = None
	while True:
		query = (
			frappe.qb.from_(sle)
			.join(item)
			.on(sle.item_code == item.name)
			.select(
				sle.name,
				sle.item_code,
				item.item_name,
				item.item_group,
				sle.warehouse,
				sle.stock_uom,
				sle.qty_after_transaction,
				sle.valuation_rate,
				sle.stock_value,
				sle.posting_datetime,
				sle.creation,
			)
			.where(sle.company == scope.company)
			.where(sle.is_cancelled == 0)
			.where(sle.posting_date <= scope.period_to)
		)
		if cursor:
			item_code, warehouse, posting_datetime, creation, name = cursor
			query = query.where(
				(sle.item_code > item_code)
				| ((sle.item_code == item_code) & (sle.warehouse > warehouse))
				| (
					(sle.item_code == item_code)
					& (sle.warehouse == warehouse)
					& (sle.posting_datetime > posting_datetime)
				)
				| (
					(sle.item_code == item_code)
					& (sle.warehouse == warehouse)
					& (sle.posting_datetime == posting_datetime)
					& (sle.creation > creation)
				)
				| (
					(sle.item_code == item_code)
					& (sle.warehouse == warehouse)
					& (sle.posting_datetime == posting_datetime)
					& (sle.creation == creation)
					& (sle.name > name)
				)
			)
		page = (
			query.orderby(sle.item_code, sle.warehouse, sle.posting_datetime, sle.creation, sle.name)
			.limit(page_size)
			.run(as_dict=True)
		)
		if not page:
			break
		yield from page
		last = page[-1]
		cursor = (last.item_code, last.warehouse, last.posting_datetime, last.creation, last.name)
		if len(page) < page_size:
			break


def reconcile_inventory(
	scope: BookScope,
	*,
	balances: Iterable[Mapping] | None = None,
	mappings: Sequence[Mapping] | None = None,
	physical_counts: Mapping[tuple[str, str], Decimal] | None = None,
	gl_balances: Mapping[str, Decimal] | None = None,
) -> InventoryReconciliation:
	balances = balances if balances is not None else iter_inventory_balances(scope)
	mappings = list(mappings) if mappings is not None else load_inventory_mappings(scope.company)
	physical_counts = physical_counts or {}
	rows = []
	stock_by_account: dict[str, Decimal] = {}
	total_stock_value = Decimal(0)
	unmapped = ambiguous = negative = physical_differences = 0
	seen_counts = set()
	for source in balances:
		row = dict(source)
		total_stock_value += decimal_value(row["stock_value"])
		matches = matching_mappings(row, mappings)
		cause = ""
		account = ""
		if not matches:
			unmapped += 1
			cause = "UNMAPPED"
		elif len(matches) > 1:
			ambiguous += 1
			cause = "AMBIGUOUS_MAPPING"
		else:
			account = matches[0]["inventory_account"]
			stock_by_account[account] = stock_by_account.get(account, Decimal(0)) + decimal_value(row["stock_value"])
		if decimal_value(row["book_quantity"]) < 0:
			negative += 1
			cause = _append_cause(cause, "NEGATIVE_INVENTORY")
		key = (row["item_code"], row["warehouse"])
		counted = physical_counts.get(key)
		seen_counts.add(key)
		quantity_difference = None if counted is None else counted - decimal_value(row["book_quantity"])
		if quantity_difference:
			physical_differences += 1
			cause = _append_cause(cause, "PHYSICAL_COUNT_DIFFERENCE")
		row.update(
			row_type="DETAIL",
			counted_quantity=counted,
			quantity_difference=quantity_difference,
			inventory_account=account,
			gl_value=None,
			value_difference=None,
			cause=cause,
		)
		rows.append(row)
	for key, counted in sorted(physical_counts.items()):
		if key not in seen_counts and counted:
			physical_differences += 1
			rows.append(_count_only_row(key, counted))
	accounts = sorted({mapping["inventory_account"] for mapping in mappings if mapping.get("inventory_account")})
	gl_balances = dict(gl_balances) if gl_balances is not None else inventory_gl_balances(scope, accounts)
	for account in sorted(set(accounts) | set(stock_by_account) | set(gl_balances)):
		stock_value = stock_by_account.get(account, Decimal(0))
		gl_value = decimal_value(gl_balances.get(account))
		rows.append(_account_row(account, stock_value, gl_value))
	total_gl_value = sum((decimal_value(value) for value in gl_balances.values()), Decimal(0))
	rows.insert(0, _summary_row(total_stock_value, total_gl_value))
	rows.append(_declaration_row())
	return InventoryReconciliation(
		rows=tuple(rows),
		stock_value=total_stock_value,
		gl_value=total_gl_value,
		unmapped=unmapped,
		ambiguous=ambiguous,
		negative=negative,
		physical_differences=physical_differences,
	)


def inventory_dataset(scope: BookScope, *, physical_count_import: str | None = None) -> BookDataset:
	counts = load_physical_counts(physical_count_import) if physical_count_import else {}
	reconciliation = reconcile_inventory(scope, physical_counts=counts)
	return BookDataset(columns=INVENTORY_COLUMNS, rows=iter(reconciliation.rows))


def matching_mappings(balance: Mapping, mappings: Sequence[Mapping]) -> list[Mapping]:
	matches = []
	for mapping in mappings:
		scope_type = mapping.get("scope_type")
		if scope_type == "WAREHOUSE" and mapping.get("warehouse") == balance.get("warehouse"):
			matches.append(mapping)
		elif scope_type == "ITEM" and mapping.get("item_code") == balance.get("item_code"):
			matches.append(mapping)
		elif scope_type == "ITEM_GROUP" and mapping.get("item_group") == balance.get("item_group"):
			matches.append(mapping)
		elif (
			scope_type == "ITEM_WAREHOUSE"
			and mapping.get("item_code") == balance.get("item_code")
			and mapping.get("warehouse") == balance.get("warehouse")
		):
			matches.append(mapping)
	return matches


def load_inventory_mappings(company: str) -> list[dict]:
	import frappe

	settings = frappe.db.get_value("GT Accounting Book Settings", {"company": company}, "name")
	if not settings:
		return []
	return [
		dict(row)
		for row in frappe.get_all(
			"GT Inventory Account Mapping",
			filters={"parent": settings, "parenttype": "GT Accounting Book Settings"},
			fields=["scope_type", "warehouse", "item_code", "item_group", "inventory_account", "category"],
			order_by="idx asc",
		)
	]


def load_physical_counts(import_name: str) -> dict[tuple[str, str], Decimal]:
	import frappe

	rows = frappe.get_all(
		"GT Physical Count Row",
		filters={"parent": import_name, "parenttype": "GT Physical Count Import", "status": "Accepted"},
		fields=["item_code", "warehouse", "counted_quantity"],
		order_by="source_row asc",
	)
	return {(row.item_code, row.warehouse): decimal_value(row.counted_quantity) for row in rows}


def inventory_gl_balances(scope: BookScope, accounts: Sequence[str]) -> dict[str, Decimal]:
	if not accounts:
		return {}
	import frappe
	from frappe.query_builder.functions import Sum

	gle = frappe.qb.DocType("GL Entry")
	query = (
		frappe.qb.from_(gle)
		.select(gle.account, Sum(gle.debit - gle.credit).as_("balance"))
		.where(gle.company == scope.company)
		.where(gle.is_cancelled == 0)
		.where(gle.posting_date <= scope.period_to)
		.where(gle.account.isin(list(accounts)))
		.groupby(gle.account)
	)
	rows = apply_finance_book(query, gle, scope.finance_book).run(as_dict=True)
	return {row.account: decimal_value(row.balance) for row in rows}


def stock_integrity_issues(
	scope: BookScope, *, observed_at: datetime | None = None, check_negative: bool = True
) -> dict:
	import frappe
	from frappe.query_builder.functions import Count

	pending = frappe.db.count(
		"Repost Item Valuation",
		{
			"company": scope.company,
			"docstatus": 1,
			"posting_date": ["<=", scope.period_to],
			"status": ["in", ["Queued", "In Progress", "Failed"]],
		},
	)
	retroactive = 0
	if observed_at:
		sle = frappe.qb.DocType("Stock Ledger Entry")
		row = (
			frappe.qb.from_(sle)
			.select(Count(sle.name).as_("count"))
			.where(sle.company == scope.company)
			.where(sle.is_cancelled == 0)
			.where(sle.posting_date <= scope.period_to)
			.where((sle.creation > observed_at) | (sle.modified > observed_at))
		).run(as_dict=True)
		retroactive = int(row[0].count or 0) if row else 0
	negative = (
		sum(1 for row in iter_inventory_balances(scope) if decimal_value(row["book_quantity"]) < 0)
		if check_negative else 0
	)
	return {"pending_reposts": pending, "retroactive_movements": retroactive, "negative_balances": negative}


def _inventory_balance(row: Mapping) -> dict:
	return {
		"item_code": row.item_code,
		"item_name": row.item_name,
		"item_group": row.item_group,
		"warehouse": row.warehouse,
		"uom": row.stock_uom,
		"book_quantity": decimal_value(row.qty_after_transaction),
		"valuation_rate": decimal_value(row.valuation_rate),
		"stock_value": decimal_value(row.stock_value),
	}


def _account_row(account: str, stock_value: Decimal, gl_value: Decimal) -> dict:
	difference = stock_value - gl_value
	return {
		"row_type": "ACCOUNT_RECONCILIATION",
		"item_code": "",
		"item_name": "",
		"item_group": "",
		"warehouse": "",
		"uom": "",
		"book_quantity": None,
		"counted_quantity": None,
		"quantity_difference": None,
		"valuation_rate": None,
		"stock_value": stock_value,
		"inventory_account": account,
		"gl_value": gl_value,
		"value_difference": difference,
		"cause": "STOCK_GL_DIFFERENCE" if difference else "",
	}


def _summary_row(stock_value: Decimal, gl_value: Decimal) -> dict:
	row = _account_row("", stock_value, gl_value)
	row["row_type"] = "SUMMARY"
	row["cause"] = "STOCK_GL_DIFFERENCE" if stock_value != gl_value else ""
	return row


def _declaration_row() -> dict:
	return {
		"row_type": "DECLARATION",
		"item_code": "",
		"item_name": "",
		"item_group": "",
		"warehouse": "",
		"uom": "",
		"book_quantity": None,
		"counted_quantity": None,
		"quantity_difference": None,
		"valuation_rate": None,
		"stock_value": None,
		"inventory_account": "",
		"gl_value": None,
		"value_difference": None,
		"cause": "NO_IMPLICIT_TOLERANCE;TECHNICAL_DRAFT_ONLY",
	}


def _count_only_row(key: tuple[str, str], counted: Decimal) -> dict:
	return {
		"row_type": "DETAIL",
		"item_code": key[0],
		"item_name": "",
		"item_group": "",
		"warehouse": key[1],
		"uom": "",
		"book_quantity": Decimal(0),
		"counted_quantity": counted,
		"quantity_difference": counted,
		"valuation_rate": Decimal(0),
		"stock_value": Decimal(0),
		"inventory_account": "",
		"gl_value": None,
		"value_difference": None,
		"cause": "PHYSICAL_COUNT_WITHOUT_STOCK_BALANCE",
	}


def _append_cause(current: str, cause: str) -> str:
	return f"{current},{cause}" if current else cause
