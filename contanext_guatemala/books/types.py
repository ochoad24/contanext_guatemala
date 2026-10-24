from dataclasses import dataclass, field
from collections.abc import Iterator, Mapping
from datetime import date
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class CheckResult:
	code: str
	category: str
	severity: str
	status: str
	message: str
	evidence: dict[str, Any] = field(default_factory=dict)

	@property
	def blocks(self) -> bool:
		return self.status == "FAIL" and self.severity in {"ERROR", "BLOCKER"}


@dataclass(frozen=True, slots=True)
class BookScope:
	company: str
	period_from: date
	period_to: date
	fiscal_year: str
	finance_book: str | None = None
	currency: str = "GTQ"


@dataclass(frozen=True, slots=True)
class BookDataset:
	columns: tuple[str, ...]
	rows: Iterator[Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class MovementTotals:
	debit: Decimal
	credit: Decimal
