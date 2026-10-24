from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any


EXPECTED_ROOT_TYPES = {
	"Activos": "Asset",
	"Pasivos": "Liability",
	"Patrimonio": "Equity",
	"Ingresos": "Income",
	"Costos": "Expense",
	"Gastos": "Expense",
}


@dataclass(frozen=True, slots=True)
class CatalogFinding:
	code: str
	severity: str
	message: str
	account: str | None = None


def diagnose_template(tree: Mapping[str, Any]) -> list[CatalogFinding]:
	findings: list[CatalogFinding] = []
	for root_name, expected_type in EXPECTED_ROOT_TYPES.items():
		root = tree.get(root_name)
		if not isinstance(root, Mapping):
			findings.append(CatalogFinding("MISSING_ROOT", "BLOCKER", f"Falta la raíz {root_name}.", root_name))
		elif root.get("root_type") != expected_type:
			findings.append(
				CatalogFinding(
					"INVALID_ROOT_TYPE",
					"BLOCKER",
					f"{root_name} debe usar root_type {expected_type}.",
					root_name,
				)
			)
	_walk_template(tree, findings)
	return findings


def _walk_template(
	node: Mapping[str, Any],
	findings: list[CatalogFinding],
	path: tuple[str, ...] = (),
) -> None:
	for name, value in node.items():
		if name in {"account_number", "account_type", "root_type", "is_group"} or not isinstance(value, Mapping):
			continue
		current_path = (*path, name)
		if "EJEMPLO" in name.upper():
			findings.append(
				CatalogFinding(
					"EXAMPLE_ACCOUNT",
					"BLOCKER",
					"Cuenta de ejemplo no permitida.",
					" / ".join(current_path),
				)
			)
		_walk_template(value, findings, current_path)


def diagnose_accounts(accounts: Iterable[Mapping[str, Any]]) -> list[CatalogFinding]:
	findings: list[CatalogFinding] = []
	seen_numbers: dict[str, str] = {}
	observed_roots: set[str] = set()
	for account in accounts:
		name = str(account.get("name") or "")
		account_name = str(account.get("account_name") or name)
		number = str(account.get("account_number") or "").strip()
		if not account.get("parent_account") and account_name in EXPECTED_ROOT_TYPES:
			observed_roots.add(account_name)
			expected_type = EXPECTED_ROOT_TYPES[account_name]
			if account.get("root_type") != expected_type:
				findings.append(
					CatalogFinding(
						"INVALID_ROOT_TYPE",
						"BLOCKER",
						f"{account_name} debe usar root_type {expected_type}.",
						name,
					)
				)
		if "EJEMPLO" in name.upper():
			findings.append(CatalogFinding("EXAMPLE_ACCOUNT", "BLOCKER", "Cuenta de ejemplo no permitida.", name))
		if not account.get("is_group") and not number:
			findings.append(
				CatalogFinding(
					"MISSING_ACCOUNT_NUMBER",
					"BLOCKER",
					"Cuenta de movimiento sin número.",
					name,
				)
			)
		if number:
			if number in seen_numbers:
				findings.append(
					CatalogFinding(
						"DUPLICATE_ACCOUNT_NUMBER",
						"BLOCKER",
						f"Número duplicado con {seen_numbers[number]}.",
						name,
					)
				)
			else:
				seen_numbers[number] = name
	for root_name in EXPECTED_ROOT_TYPES.keys() - observed_roots:
		findings.append(
			CatalogFinding("MISSING_ROOT", "BLOCKER", f"Falta la raíz {root_name}.", root_name)
		)
	return findings


def diagnose_company_catalog(company: str) -> list[CatalogFinding]:
	"""Read-only adapter. It never updates Account or accounting transactions."""
	if not company:
		raise ValueError("La empresa es obligatoria.")
	import frappe

	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "disabled": 0},
		fields=["name", "account_name", "account_number", "is_group", "parent_account", "root_type"],
		order_by="lft asc, name asc",
	)
	return diagnose_accounts(accounts)
