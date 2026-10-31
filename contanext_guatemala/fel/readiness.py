from __future__ import annotations

from dataclasses import asdict, dataclass

import frappe

from contanext_guatemala.fel.settings import FELConfigurationError, validate_tekra_environment


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
	code: str
	status: str
	message: str
	count: int = 0


def diagnose_fel_readiness(company: str) -> dict[str, object]:
	"""Inspect existing data without assigning or changing fiscal values."""
	company_values = frappe.db.get_value(
		"Company",
		company,
		[
			"company_name",
			"tax_id",
			"contanext_gt_fiscal_address",
			"contanext_gt_fel_provider",
			"contanext_gt_fel_policy",
			"contanext_gt_vat_affiliation",
			"contanext_gt_price_tax_mode",
			"contanext_gt_tekra_environment",
			"contanext_gt_default_establishment",
		],
		as_dict=True,
	)
	if not company_values:
		raise frappe.DoesNotExistError(company)

	checks = [
		_required_check("IDENTITY", company_values.company_name and company_values.tax_id, "Razón social y NIT"),
		_required_check(
			"FISCAL_CONFIGURATION",
			company_values.contanext_gt_vat_affiliation and company_values.contanext_gt_price_tax_mode,
			"Afiliación IVA y tratamiento de precios",
		),
		_required_check(
			"DEFAULT_ESTABLISHMENT",
			company_values.contanext_gt_default_establishment,
			"Establecimiento predeterminado",
		),
	]

	active_establishments = frappe.db.count("GT FEL Establishment", {"company": company, "is_active": 1})
	checks.append(
		ReadinessCheck(
			code="ACTIVE_ESTABLISHMENTS",
			status="PASS" if active_establishments else "FAIL",
			message="Establecimientos activos configurados",
			count=active_establishments,
		)
	)

	missing_item_kind = frappe.db.count("Item", {"disabled": 0, "contanext_gt_fel_item_kind": ["is", "not set"]})
	checks.append(_count_check("ITEM_KIND", missing_item_kind, "Ítems activos sin clasificación B/S"))

	selected_customers = frappe.get_all(
		"Customer",
		filters={"disabled": 0, "contanext_gt_fel_selected": 1},
		fields=["name", "tax_id", "contanext_gt_identification_type"],
	)
	incomplete_customers = sum(
		1 for customer in selected_customers if not customer.tax_id or not customer.contanext_gt_identification_type
	)
	checks.append(_count_check("CUSTOMER_IDENTIFICATION", incomplete_customers, "Clientes FEL sin identificación completa"))

	try:
		validate_tekra_environment(company_values.contanext_gt_tekra_environment or "SANDBOX")
	except FELConfigurationError as exc:
		checks.append(ReadinessCheck("ENVIRONMENT", "FAIL", str(exc)))
	else:
		checks.append(ReadinessCheck("ENVIRONMENT", "PASS", "Variables TEKRA completas para el ambiente"))

	return {
		"company": company,
		"ready": all(check.status == "PASS" for check in checks),
		"checks": [asdict(check) for check in checks],
	}


def _required_check(code: str, value, label: str) -> ReadinessCheck:
	return ReadinessCheck(code, "PASS" if value else "FAIL", f"{label}: {'completo' if value else 'pendiente'}")


def _count_check(code: str, count: int, label: str) -> ReadinessCheck:
	return ReadinessCheck(code, "PASS" if count == 0 else "FAIL", label, count=count)
