from dataclasses import dataclass

import frappe

from contanext_guatemala.fel.provider import is_fel_provider_registered
from contanext_guatemala.fiscal.company import (
	FiscalAddress,
	get_company_fiscal_configuration,
)
from contanext_guatemala.validation import validate_nit_format


@dataclass(frozen=True, slots=True)
class FELConfiguration:
	company: str
	enabled: bool
	provider: str | None
	legal_name: str
	nit: str | None
	trade_name: str | None
	establishment_code: str | None
	fiscal_address: FiscalAddress | None
	policy: str = "NEVER"
	vat_affiliation: str | None = None
	price_tax_mode: str | None = None
	environment: str = "SANDBOX"
	origin_id: str | None = None
	sign_issuer: bool = True
	default_establishment: str | None = None
	phrases: tuple[dict[str, object], ...] = ()


def get_fel_configuration(company: str) -> FELConfiguration:
	"""Resolve and validate the FEL configuration owned by one Company."""
	company_configuration = get_company_fiscal_configuration(company)
	provider = company_configuration.fel_provider.strip() if company_configuration.fel_provider else None

	configuration = FELConfiguration(
		company=company_configuration.company,
		enabled=company_configuration.fel_enabled,
		provider=provider,
		legal_name=company_configuration.legal_name,
		nit=company_configuration.nit,
		trade_name=company_configuration.trade_name,
		establishment_code=company_configuration.establishment_code,
		fiscal_address=company_configuration.fiscal_address,
		policy=company_configuration.fel_policy,
		vat_affiliation=company_configuration.vat_affiliation,
		price_tax_mode=company_configuration.price_tax_mode,
		environment=company_configuration.tekra_environment,
		origin_id=company_configuration.tekra_origin_id,
		sign_issuer=company_configuration.tekra_sign_issuer,
		default_establishment=company_configuration.default_establishment,
		phrases=company_configuration.fel_phrases,
	)
	if not configuration.enabled:
		return configuration

	missing = [
		label
		for value, label in (
			(configuration.legal_name, "Razón social"),
			(configuration.nit, "NIT"),
			(configuration.fiscal_address, "Dirección fiscal"),
			(configuration.establishment_code, "Código de establecimiento fiscal"),
			(configuration.provider, "Adaptador de certificador"),
		)
		if not value
	]
	if missing:
		frappe.throw(
			frappe._("La configuración FEL de la empresa {0} está incompleta. Campos: {1}.").format(
				frappe.bold(configuration.company), frappe.bold(", ".join(missing))
			)
		)

	try:
		nit = validate_nit_format(configuration.nit)
	except ValueError:
		frappe.throw(
			frappe._("La configuración FEL de la empresa {0} contiene un NIT inválido.").format(
				frappe.bold(configuration.company)
			)
		)

	if not is_fel_provider_registered(configuration.provider):
		frappe.throw(
			frappe._("El adaptador FEL {0} de la empresa {1} no está registrado.").format(
				frappe.bold(configuration.provider), frappe.bold(configuration.company)
			)
		)

	return FELConfiguration(
		company=configuration.company,
		enabled=True,
		provider=configuration.provider,
		legal_name=configuration.legal_name,
		nit=nit,
		trade_name=configuration.trade_name,
		establishment_code=configuration.establishment_code,
		fiscal_address=configuration.fiscal_address,
		policy=configuration.policy,
		vat_affiliation=configuration.vat_affiliation,
		price_tax_mode=configuration.price_tax_mode,
		environment=configuration.environment,
		origin_id=configuration.origin_id,
		sign_issuer=configuration.sign_issuer,
		default_establishment=configuration.default_establishment,
		phrases=configuration.phrases,
	)
