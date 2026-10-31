from dataclasses import asdict, dataclass

import frappe
from frappe.contacts.doctype.address.address import get_address_display

from contanext_guatemala.fel.provider import is_fel_provider_registered
from contanext_guatemala.validation import validate_nit_format


COMPANY_GT_CONFIGURATION_FIELDS = (
	"contanext_gt_trade_name",
	"contanext_gt_fiscal_address",
	"contanext_gt_establishment_code",
	"contanext_gt_accounting_framework",
	"contanext_gt_legal_representative_name",
	"contanext_gt_legal_representative_id",
	"contanext_gt_accountant_name",
	"contanext_gt_accountant_nit",
	"contanext_gt_accountant_registration",
	"contanext_gt_accountant_email",
	"contanext_gt_fel_enabled",
	"contanext_gt_fel_provider",
	"contanext_gt_fel_policy",
	"contanext_gt_vat_affiliation",
	"contanext_gt_price_tax_mode",
	"contanext_gt_fel_phrases",
	"contanext_gt_tekra_environment",
	"contanext_gt_tekra_origin_id",
	"contanext_gt_tekra_sign_issuer",
	"contanext_gt_default_establishment",
)
COMPANY_FEL_CONFIGURATION_FIELDS = frozenset(
	{
		"contanext_gt_fel_enabled",
		"contanext_gt_fel_provider",
		"contanext_gt_fel_policy",
		"contanext_gt_vat_affiliation",
		"contanext_gt_price_tax_mode",
		"contanext_gt_fel_phrases",
		"contanext_gt_tekra_environment",
		"contanext_gt_tekra_origin_id",
		"contanext_gt_tekra_sign_issuer",
		"contanext_gt_default_establishment",
	}
)

COMPANY_FISCAL_PROTECTED_FIELDS = (
	"company_name",
	"tax_id",
	*COMPANY_GT_CONFIGURATION_FIELDS,
)

COMPANY_FISCAL_EDITOR_ROLES = frozenset({"System Manager", "GT Books Manager"})


@dataclass(frozen=True, slots=True)
class FiscalAddress:
	address_name: str
	address_line1: str
	address_line2: str | None
	city: str
	state: str | None
	pincode: str | None
	country: str
	display: str


@dataclass(frozen=True, slots=True)
class CompanyFiscalConfiguration:
	company: str
	legal_name: str
	nit: str | None
	trade_name: str | None
	fiscal_address_name: str | None
	establishment_code: str | None
	accounting_framework: str | None
	legal_representative_name: str | None
	legal_representative_id: str | None
	accountant_name: str | None
	accountant_nit: str | None
	accountant_registration: str | None
	accountant_email: str | None
	country: str
	currency: str
	fel_enabled: bool
	fel_provider: str | None
	fiscal_address: FiscalAddress | None
	fel_policy: str = "NEVER"
	vat_affiliation: str | None = None
	price_tax_mode: str | None = None
	tekra_environment: str = "SANDBOX"
	tekra_origin_id: str | None = None
	tekra_sign_issuer: bool = True
	default_establishment: str | None = None
	fel_phrases: tuple[dict[str, object], ...] = ()


def get_company_fiscal_configuration(
	company: str,
	*,
	include_protected: bool = False,
) -> CompanyFiscalConfiguration:
	"""Resolve fiscal identity exclusively from Company and its selected Address."""
	company_doc = frappe.get_doc("Company", company)
	legal_representative_id = None
	if include_protected:
		legal_representative_id = company_doc.get_password(
			"contanext_gt_legal_representative_id", raise_exception=False
		)

	return CompanyFiscalConfiguration(
		company=company_doc.name,
		legal_name=company_doc.company_name,
		nit=company_doc.tax_id or None,
		trade_name=company_doc.get("contanext_gt_trade_name") or None,
		fiscal_address_name=company_doc.get("contanext_gt_fiscal_address") or None,
		establishment_code=company_doc.get("contanext_gt_establishment_code") or None,
		accounting_framework=company_doc.get("contanext_gt_accounting_framework") or None,
		legal_representative_name=company_doc.get("contanext_gt_legal_representative_name") or None,
		legal_representative_id=legal_representative_id,
		accountant_name=company_doc.get("contanext_gt_accountant_name") or None,
		accountant_nit=company_doc.get("contanext_gt_accountant_nit") or None,
		accountant_registration=company_doc.get("contanext_gt_accountant_registration") or None,
		accountant_email=company_doc.get("contanext_gt_accountant_email") or None,
		country=company_doc.country,
		currency=company_doc.default_currency,
		fel_enabled=bool(company_doc.get("contanext_gt_fel_enabled")),
		fel_provider=company_doc.get("contanext_gt_fel_provider") or None,
		fiscal_address=get_company_fiscal_address(company_doc.name),
		fel_policy=company_doc.get("contanext_gt_fel_policy") or "NEVER",
		vat_affiliation=company_doc.get("contanext_gt_vat_affiliation") or None,
		price_tax_mode=company_doc.get("contanext_gt_price_tax_mode") or None,
		tekra_environment=company_doc.get("contanext_gt_tekra_environment") or "SANDBOX",
		tekra_origin_id=company_doc.get("contanext_gt_tekra_origin_id") or None,
		tekra_sign_issuer=(
			True
			if company_doc.get("contanext_gt_tekra_sign_issuer") is None
			else bool(company_doc.get("contanext_gt_tekra_sign_issuer"))
		),
		default_establishment=company_doc.get("contanext_gt_default_establishment") or None,
		fel_phrases=tuple(
			{
				"phrase_type": row.phrase_type,
				"scenario_code": row.scenario_code,
				"valid_from": row.valid_from,
				"valid_until": row.valid_until,
				"source": row.source,
			}
			for row in company_doc.get("contanext_gt_fel_phrases", [])
		),
	)


def get_company_fiscal_address(company: str) -> FiscalAddress | None:
	"""Resolve and validate the Address selected by a Company."""
	company_doc = frappe.get_doc("Company", company)
	address_name = company_doc.get("contanext_gt_fiscal_address")
	if not address_name:
		return None

	validate_company_fiscal_address(company_doc)
	address = frappe.get_doc("Address", address_name)
	return FiscalAddress(
		address_name=address.name,
		address_line1=address.address_line1,
		address_line2=address.address_line2 or None,
		city=address.city,
		state=address.state or None,
		pincode=address.pincode or None,
		country=address.country,
		display=get_address_display(address.as_dict()),
	)


def build_company_fiscal_snapshot(company: str) -> dict[str, object]:
	"""Build the stable fiscal, accountant and representative payloads for a run."""
	configuration = get_company_fiscal_configuration(company)
	return {
		"identity": {
			"company": configuration.company,
			"legal_name": configuration.legal_name,
			"nit": configuration.nit,
			"trade_name": configuration.trade_name,
			"fiscal_address_name": configuration.fiscal_address_name,
			"fiscal_address": asdict(configuration.fiscal_address)
			if configuration.fiscal_address
			else None,
			"establishment_code": configuration.establishment_code,
			"accounting_framework": configuration.accounting_framework,
			"currency": configuration.currency,
			"language": "Español",
		},
		"accountant": {
			"name": configuration.accountant_name,
			"nit": configuration.accountant_nit,
			"registration": configuration.accountant_registration,
			"email": configuration.accountant_email,
		},
		"representative": {
			"name": configuration.legal_representative_name,
		},
	}


def validate_company_fiscal_configuration(doc, method=None) -> None:
	"""Apply country-scoped fiscal rules without requiring initial completeness."""
	validate_company_fiscal_changes(doc)
	validate_company_gt_country(doc)
	if doc.country == "Guatemala":
		validate_company_nits(doc)
		validate_company_fiscal_address(doc)
		validate_company_fel_activation(doc)


def validate_company_fiscal_changes(doc) -> None:
	"""Reject persisted fiscal changes made without an approved editor role."""
	is_new = getattr(doc, "is_new", None)
	if not callable(is_new) or is_new():
		return

	previous = doc.get_doc_before_save()
	if not previous:
		return

	changed_fields = [
		fieldname
		for fieldname in COMPANY_FISCAL_PROTECTED_FIELDS
		if doc.get(fieldname) != previous.get(fieldname)
	]
	roles = set(frappe.get_roles())
	if not changed_fields or COMPANY_FISCAL_EDITOR_ROLES.intersection(roles):
		return
	if set(changed_fields).issubset(COMPANY_FEL_CONFIGURATION_FIELDS) and "GT FEL Manager" in roles:
		return

	meta = frappe.get_meta("Company")
	labels = [
		meta.get_label(fieldname) or fieldname
		for fieldname in changed_fields
	]
	frappe.throw(
		frappe._(
			"Solo System Manager o GT Books Manager pueden modificar datos fiscales de la empresa. Campos modificados: {0}."
		).format(frappe.bold(", ".join(labels))),
		frappe.PermissionError,
	)


def validate_company_gt_country(doc) -> None:
	"""Reject Guatemala-specific configuration on companies from other countries."""
	if doc.country == "Guatemala":
		return

	configured_fields = [
		fieldname for fieldname in COMPANY_GT_CONFIGURATION_FIELDS if doc.get(fieldname)
	]
	if configured_fields:
		frappe.throw(
			frappe._(
				"La configuración fiscal de ContaNext para Guatemala solo puede usarse en empresas cuyo país sea Guatemala."
			)
		)


def validate_company_nits(doc) -> None:
	"""Normalize and validate optional Company and accountant NIT values."""
	for fieldname, label in (
		("tax_id", "NIT de la empresa"),
		("contanext_gt_accountant_nit", "NIT del contador"),
	):
		try:
			setattr(doc, fieldname, validate_nit_format(doc.get(fieldname), allow_empty=True))
		except ValueError:
			frappe.throw(frappe._("{0} tiene un formato inválido.").format(label))


def validate_company_fiscal_address(doc, method=None) -> None:
	"""Validate that the selected fiscal address belongs to this company."""
	address_name = doc.get("contanext_gt_fiscal_address")
	if not address_name:
		return

	address = frappe.db.get_value(
		"Address",
		address_name,
		("disabled", "is_your_company_address"),
		as_dict=True,
	)
	if not address:
		frappe.throw(
			frappe._("La dirección fiscal {0} no existe.").format(frappe.bold(address_name))
		)
	if address.disabled:
		frappe.throw(
			frappe._("La dirección fiscal {0} está deshabilitada.").format(frappe.bold(address_name))
		)
	if not address.is_your_company_address:
		frappe.throw(
			frappe._("La dirección fiscal {0} no es una dirección de la empresa.").format(
				frappe.bold(address_name)
			)
		)

	is_linked_to_company = frappe.db.exists(
		"Dynamic Link",
		{
			"parent": address_name,
			"parenttype": "Address",
			"parentfield": "links",
			"link_doctype": "Company",
			"link_name": doc.name,
		},
	)
	if not is_linked_to_company:
		frappe.throw(
			frappe._("La dirección fiscal {0} no está vinculada a la empresa {1}.").format(
				frappe.bold(address_name), frappe.bold(doc.name)
			)
		)


def validate_company_fel_activation(doc) -> None:
	"""Require complete valid identity and a registered adapter when FEL is enabled."""
	if not doc.get("contanext_gt_fel_enabled"):
		return

	required_fields = {
		"company_name": "Razón social",
		"tax_id": "NIT",
		"contanext_gt_fiscal_address": "Dirección fiscal",
		"contanext_gt_establishment_code": "Código de establecimiento fiscal",
		"contanext_gt_fel_provider": "Adaptador de certificador",
	}
	missing = [label for fieldname, label in required_fields.items() if not doc.get(fieldname)]
	if missing:
		frappe.throw(
			frappe._("No se puede habilitar FEL. Complete los campos: {0}.").format(
				frappe.bold(", ".join(missing))
			)
		)

	try:
		doc.tax_id = validate_nit_format(doc.tax_id)
	except ValueError:
		frappe.throw(
			frappe._("No se puede habilitar FEL porque el NIT de la empresa tiene un formato inválido.")
		)

	provider_name = doc.get("contanext_gt_fel_provider").strip()
	doc.contanext_gt_fel_provider = provider_name
	if not is_fel_provider_registered(provider_name):
		frappe.throw(
			frappe._(
				"No se puede habilitar FEL porque el adaptador {0} no está registrado por la aplicación."
			).format(frappe.bold(provider_name))
		)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_company_fiscal_address_options(
	doctype: str,
	txt: str,
	searchfield: str,
	start: int,
	page_len: int,
	filters: dict[str, str],
) -> list[tuple[str, ...]]:
	"""Return active company addresses eligible for fiscal configuration."""
	filters = frappe.parse_json(filters) or {}
	company = filters.get("company")
	if not company:
		return []

	frappe.has_permission("Company", ptype="select", doc=company, throw=True)

	address = frappe.qb.DocType("Address")
	dynamic_link = frappe.qb.DocType("Dynamic Link")
	search_text = f"%{txt}%"

	query = (
		frappe.qb.from_(address)
		.inner_join(dynamic_link)
		.on(
			(address.name == dynamic_link.parent)
			& (dynamic_link.parenttype == "Address")
			& (dynamic_link.parentfield == "links")
		)
		.select(address.name, address.address_title, address.address_line1, address.city)
		.distinct()
		.where(
			(dynamic_link.link_doctype == "Company")
			& (dynamic_link.link_name == company)
			& (address.is_your_company_address == 1)
			& (address.disabled == 0)
			& (
				(address.name.like(search_text))
				| (address.address_title.like(search_text))
				| (address.address_line1.like(search_text))
				| (address.city.like(search_text))
			)
		)
		.orderby(address.name)
		.offset(start)
		.limit(page_len)
	)
	return query.run(as_list=True)
