from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class FELStatus(StrEnum):
	PENDING = "PENDING"
	PROCESSING = "PROCESSING"
	CERTIFIED = "CERTIFIED"
	REJECTED = "REJECTED"
	CANCELLED = "CANCELLED"
	FAILED = "FAILED"


@dataclass(frozen=True)
class CertificationRequest:
	document_type: str
	external_id: str
	xml: bytes
	metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CertificationResult:
	status: FELStatus
	uuid: str | None = None
	certified_xml: bytes | None = None
	provider_reference: str | None = None
	errors: tuple[str, ...] = ()
