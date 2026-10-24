from enum import StrEnum


UNAUTHORIZED_DRAFT_LABEL = "NO AUTORIZADO — SOLO VALIDACIÓN TÉCNICA"
SNAPSHOT_SCHEMA = "contanext.gt.accounting-book.snapshot"
SNAPSHOT_VERSION = 1
FOLIO_MARKER_PREFIX = "FOLIO-"


class BookRunStatus(StrEnum):
	DRAFT = "Draft"
	QUEUED = "Queued"
	GENERATED = "Generated"
	VALIDATION_FAILED = "Validation Failed"
	READY_FOR_REVIEW = "Ready for Review"
	APPROVED = "Approved"
	REJECTED = "Rejected"
	SEALING = "Sealing"
	AWAITING_PRINT_CONFIRMATION = "Awaiting Print Confirmation"
	PRINT_EXCEPTION = "Print Exception"
	SEALED = "Sealed"
	SEAL_FAILED = "Seal Failed"
	SUPERSEDED = "Superseded"


class BookType(StrEnum):
	INVENTORY = "INVENTORY"
	JOURNAL = "JOURNAL"
	LEDGER = "LEDGER"
	TRIAL_BALANCE = "TRIAL_BALANCE"
	FINANCIAL_STATEMENTS = "FINANCIAL_STATEMENTS"
