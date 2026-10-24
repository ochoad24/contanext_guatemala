from collections.abc import Iterator

from contanext_guatemala.books.gl import decimal_value, iter_gl_entries
from contanext_guatemala.books.types import BookDataset, BookScope


JOURNAL_COLUMNS = (
	"entry_sequence",
	"line_sequence",
	"posting_date",
	"voucher_type",
	"voucher_no",
	"concept",
	"account_number",
	"account",
	"account_name",
	"party_type",
	"party",
	"cost_center",
	"project",
	"against",
	"debit",
	"credit",
	"source_gl_entry",
)


def journal_dataset(scope: BookScope, *, page_size: int = 5_000) -> BookDataset:
	return BookDataset(columns=JOURNAL_COLUMNS, rows=iter_journal_rows(scope, page_size=page_size))


def iter_journal_rows(scope: BookScope, *, page_size: int = 5_000) -> Iterator[dict]:
	entry_sequence = 0
	line_sequence = 0
	previous_voucher = None
	for source in iter_gl_entries(scope, order="journal", page_size=page_size):
		voucher = (source.posting_date, source.voucher_type, source.voucher_no)
		if voucher != previous_voucher:
			entry_sequence += 1
			line_sequence = 0
			previous_voucher = voucher
		line_sequence += 1
		yield {
			"entry_sequence": entry_sequence,
			"line_sequence": line_sequence,
			"posting_date": source.posting_date,
			"voucher_type": source.voucher_type,
			"voucher_no": source.voucher_no,
			"concept": source.remarks or "",
			"account_number": source.account_number or "",
			"account": source.account,
			"account_name": source.account_name,
			"party_type": source.party_type or "",
			"party": source.party or "",
			"cost_center": source.cost_center or "",
			"project": source.project or "",
			"against": source.against or "",
			"debit": decimal_value(source.debit),
			"credit": decimal_value(source.credit),
			"source_gl_entry": source.name,
		}
