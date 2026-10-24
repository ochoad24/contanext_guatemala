from typing import Any

from contanext_guatemala.books.constants import SNAPSHOT_SCHEMA, SNAPSHOT_VERSION
from contanext_guatemala.books.requirements import PACKAGE_SCHEMA, PACKAGE_VERSION
from contanext_guatemala.books.snapshots import canonical_json, sha256_hex


UPGRADE_CONTRACT_SCHEMA = "contanext.gt.accounting-book.upgrade-contract"
UPGRADE_CONTRACT_VERSION = 1
SOURCE_ORDER_VERSION = 1
SUPPORTED_ERPNEXT_MAJOR = 16
SUPPORTED_FRAPPE_MAJOR = 16


def build_upgrade_contract() -> dict[str, Any]:
	"""Return the stable contract that an ERPNext/Frappe upgrade must preserve."""
	payload: dict[str, Any] = {
		"schema": UPGRADE_CONTRACT_SCHEMA,
		"version": UPGRADE_CONTRACT_VERSION,
		"supported_majors": {"erpnext": SUPPORTED_ERPNEXT_MAJOR, "frappe": SUPPORTED_FRAPPE_MAJOR},
		"snapshot": {"schema": SNAPSHOT_SCHEMA, "version": SNAPSHOT_VERSION},
		"requirement_package": {"schema": PACKAGE_SCHEMA, "version": PACKAGE_VERSION},
		"source_order_version": SOURCE_ORDER_VERSION,
		"required_invariants": [
			"debits_equal_credits",
			"journal_equals_ledger_equals_trial_balance",
			"assets_equal_liabilities_plus_equity",
			"stable_row_order",
			"private_artifacts",
			"cross_company_access_denied",
		],
	}
	payload["contract_sha256"] = sha256_hex(canonical_json(payload))
	return payload


def assert_supported_runtime(*, frappe_version: str, erpnext_version: str) -> None:
	for component, value, expected in (
		("Frappe", frappe_version, SUPPORTED_FRAPPE_MAJOR),
		("ERPNext", erpnext_version, SUPPORTED_ERPNEXT_MAJOR),
	):
		try:
			major = int((value or "").lstrip("v").split(".", 1)[0])
		except (TypeError, ValueError):
			raise RuntimeError(f"No se pudo determinar la versión de {component}: {value!r}.") from None
		if major != expected:
			raise RuntimeError(
				f"{component} {value} queda fuera del contrato fijado para la versión mayor {expected}."
			)
