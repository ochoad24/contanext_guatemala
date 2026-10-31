from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class DTEType(StrEnum):
	FACT = "FACT"
	FCAM = "FCAM"
	NCRE = "NCRE"
	NDEB = "NDEB"
	FPEQ = "FPEQ"
	FCAP = "FCAP"
	FESP = "FESP"


class FELOperationType(StrEnum):
	CERTIFY = "CERTIFY"
	CANCEL = "CANCEL"
	RECONCILE = "RECONCILE"
	QUERY_CONTRIBUTOR = "QUERY_CONTRIBUTOR"


class FELStatus(StrEnum):
	PENDING = "PENDING"
	PROCESSING = "PROCESSING"
	RETRY_PENDING = "RETRY_PENDING"
	RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
	CERTIFIED = "CERTIFIED"
	REJECTED = "REJECTED"
	CANCEL_PENDING = "CANCEL_PENDING"
	CANCELLED = "CANCELLED"
	FAILED = "FAILED"


class FELErrorClassification(StrEnum):
	NONE = "NONE"
	FISCAL_REJECTION = "FISCAL_REJECTION"
	XSD_REJECTION = "XSD_REJECTION"
	TRANSIENT = "TRANSIENT"
	UNCERTAIN = "UNCERTAIN"
	PERMANENT_CONFIGURATION = "PERMANENT_CONFIGURATION"
	PERMANENT_PROVIDER = "PERMANENT_PROVIDER"


class IdentificationType(StrEnum):
	NIT = "NIT"
	CUI = "CUI"


@dataclass(frozen=True, slots=True)
class CertificationRequest:
	document_type: DTEType
	external_id: str
	idempotency_key: str
	xml: bytes
	canonical_hash: str | None = None
	metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CancellationRequest:
	uuid: str
	reason: str
	xml: bytes
	original_operation: str | None = None
	metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReconciliationRequest:
	idempotency_key: str
	uuid: str | None = None
	provider_reference: str | None = None
	metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ContributorQueryRequest:
	identification_type: IdentificationType
	identifier: str
	environment: str
	force: bool = False


@dataclass(frozen=True, slots=True)
class CertificationResult:
	status: FELStatus
	error_classification: FELErrorClassification = FELErrorClassification.NONE
	uuid: str | None = None
	series: str | None = None
	number: str | None = None
	certified_at: datetime | None = None
	certifier_nit: str | None = None
	certified_xml: bytes | None = None
	pdf: bytes | None = None
	provider_reference: str | None = None
	http_status: int | None = None
	soap_code: str | None = None
	warnings: tuple[str, ...] = ()
	brand_messages: tuple[str, ...] = ()
	xsd_errors: tuple[str, ...] = ()
	errors: tuple[str, ...] = ()
	normalized_result: dict[str, Any] = field(default_factory=dict)
	raw_response: bytes | None = None


@dataclass(frozen=True, slots=True)
class ContributorQueryResult:
	status: str
	returned_name: str | None = None
	code: str | None = None
	message: str | None = None
	error_classification: FELErrorClassification = FELErrorClassification.NONE
	raw_response_hash: str | None = None
