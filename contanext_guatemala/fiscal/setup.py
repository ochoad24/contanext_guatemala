import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
from frappe.permissions import add_permission, get_rights, update_permission_property


COMPANY_FISCAL_FIELDNAMES = (
	"contanext_gt_fiscal_tab",
	"contanext_gt_identity_section",
	"contanext_gt_identity_summary",
	"contanext_gt_trade_name",
	"contanext_gt_fiscal_address",
	"contanext_gt_establishment_code",
	"contanext_gt_books_section",
	"contanext_gt_accounting_framework",
	"contanext_gt_signers_section",
	"contanext_gt_legal_representative_name",
	"contanext_gt_legal_representative_id",
	"contanext_gt_accountant_name",
	"contanext_gt_accountant_nit",
	"contanext_gt_accountant_registration",
	"contanext_gt_accountant_email",
	"contanext_gt_fel_section",
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
	"contanext_gt_fel_notice",
)

COMPANY_FISCAL_NON_SECRET_FIELDNAMES = (
	"contanext_gt_trade_name",
	"contanext_gt_fiscal_address",
	"contanext_gt_establishment_code",
	"contanext_gt_accounting_framework",
	"contanext_gt_legal_representative_name",
	"contanext_gt_accountant_name",
	"contanext_gt_accountant_nit",
	"contanext_gt_accountant_registration",
	"contanext_gt_accountant_email",
)

COMPANY_FISCAL_SECRET_FIELDNAMES = (
	"contanext_gt_legal_representative_id",
)
COMPANY_FEL_PERMISSION_FIELDNAMES = frozenset(
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

COMPANY_FISCAL_PERMISSION_MATRIX = {
	0: {
		"GT Books Manager": frozenset({"read", "write"}),
		"GT Books Reviewer": frozenset({"read"}),
		"GT Books Auditor": frozenset({"read"}),
	},
	1: {
		"System Manager": frozenset({"read", "write", "create"}),
		"GT Books Manager": frozenset({"read", "write", "create"}),
		"Accounts Manager": frozenset({"read"}),
		"GT Books Reviewer": frozenset({"read"}),
		"GT Books Auditor": frozenset({"read"}),
	},
	2: {
		"System Manager": frozenset({"read", "write", "create"}),
		"GT Books Manager": frozenset({"read", "write", "create"}),
	},
	3: {
		"System Manager": frozenset({"read", "write", "create"}),
		"GT FEL Manager": frozenset({"read", "write", "create"}),
		"GT FEL Auditor": frozenset({"read"}),
	},
}


def get_company_fiscal_custom_fields() -> dict[str, list[dict[str, object]]]:
	"""Return the canonical Company field definitions in display order."""
	fields = [
		{
			"fieldname": "contanext_gt_fiscal_tab",
			"label": "Configuración fiscal de ContaNext",
			"fieldtype": "Tab Break",
			"insert_after": "dashboard_tab",
			"depends_on": 'eval:doc.country==="Guatemala"',
		},
		{
			"fieldname": "contanext_gt_identity_section",
			"label": "Identidad fiscal",
			"fieldtype": "Section Break",
		},
		{
			"fieldname": "contanext_gt_identity_summary",
			"label": "Razón social y NIT",
			"fieldtype": "HTML",
		},
		{
			"fieldname": "contanext_gt_trade_name",
			"label": "Nombre comercial",
			"fieldtype": "Data",
		},
		{
			"fieldname": "contanext_gt_fiscal_address",
			"label": "Dirección fiscal",
			"fieldtype": "Link",
			"options": "Address",
		},
		{
			"fieldname": "contanext_gt_establishment_code",
			"label": "Código de establecimiento fiscal",
			"fieldtype": "Data",
		},
		{
			"fieldname": "contanext_gt_books_section",
			"label": "Información contable",
			"fieldtype": "Section Break",
		},
		{
			"fieldname": "contanext_gt_accounting_framework",
			"label": "Marco contable",
			"fieldtype": "Select",
			"options": "\nNIIF\nNIIF para PYMES\nBase especial aprobada",
		},
		{
			"fieldname": "contanext_gt_signers_section",
			"label": "Responsables",
			"fieldtype": "Section Break",
		},
		{
			"fieldname": "contanext_gt_legal_representative_name",
			"label": "Representante legal",
			"fieldtype": "Data",
		},
		{
			"fieldname": "contanext_gt_legal_representative_id",
			"label": "Identificación del representante",
			"fieldtype": "Password",
		},
		{
			"fieldname": "contanext_gt_accountant_name",
			"label": "Contador",
			"fieldtype": "Data",
		},
		{
			"fieldname": "contanext_gt_accountant_nit",
			"label": "NIT del contador",
			"fieldtype": "Data",
		},
		{
			"fieldname": "contanext_gt_accountant_registration",
			"label": "Registro profesional del contador",
			"fieldtype": "Data",
		},
		{
			"fieldname": "contanext_gt_accountant_email",
			"label": "Correo del contador",
			"fieldtype": "Data",
			"options": "Email",
		},
		{
			"fieldname": "contanext_gt_fel_section",
			"label": "Factura Electrónica en Línea — FEL",
			"fieldtype": "Section Break",
		},
		{
			"fieldname": "contanext_gt_fel_enabled",
			"label": "FEL habilitado",
			"fieldtype": "Check",
			"default": "0",
		},
		{
			"fieldname": "contanext_gt_fel_provider",
			"label": "Adaptador de certificador",
			"fieldtype": "Select",
			"options": "\nTEKRA",
			"depends_on": "eval:doc.contanext_gt_fel_enabled",
		},
		{
			"fieldname": "contanext_gt_fel_policy",
			"label": "Política FEL",
			"fieldtype": "Select",
			"options": "NEVER\nALWAYS\nSELECTED_CUSTOMERS\nASK_EACH_TIME",
			"default": "NEVER",
		},
		{
			"fieldname": "contanext_gt_vat_affiliation",
			"label": "Afiliación IVA",
			"fieldtype": "Select",
			"options": "\nGEN\nPEQ",
		},
		{
			"fieldname": "contanext_gt_price_tax_mode",
			"label": "Tratamiento de precios",
			"fieldtype": "Select",
			"options": "\nTAX_INCLUDED\nTAX_EXCLUDED",
		},
		{
			"fieldname": "contanext_gt_fel_phrases",
			"label": "Frases FEL",
			"fieldtype": "Table",
			"options": "GT FEL Phrase",
		},
		{
			"fieldname": "contanext_gt_tekra_environment",
			"label": "Ambiente TEKRA",
			"fieldtype": "Select",
			"options": "SANDBOX\nPRODUCTION",
			"default": "SANDBOX",
		},
		{
			"fieldname": "contanext_gt_tekra_origin_id",
			"label": "Identificador de origen TEKRA",
			"fieldtype": "Data",
		},
		{
			"fieldname": "contanext_gt_tekra_sign_issuer",
			"label": "Solicitar firma de emisor a TEKRA",
			"fieldtype": "Check",
			"default": "1",
		},
		{
			"fieldname": "contanext_gt_default_establishment",
			"label": "Establecimiento FEL predeterminado",
			"fieldtype": "Link",
			"options": "GT FEL Establishment",
		},
		{
			"fieldname": "contanext_gt_fel_notice",
			"label": "Advertencia FEL",
			"fieldtype": "HTML",
			"options": (
				'<div class="alert alert-warning">'
				"La activación FEL requiere preflight completo, variables de entorno y homologación."
				"</div>"
			),
		},
	]

	for previous, field in zip(
		("dashboard_tab", *COMPANY_FISCAL_FIELDNAMES[:-1]), fields, strict=True
	):
		field.setdefault("insert_after", previous)
		if field["fieldname"] in COMPANY_FEL_PERMISSION_FIELDNAMES:
			field["permlevel"] = 3
		elif field["fieldname"] in COMPANY_FISCAL_NON_SECRET_FIELDNAMES:
			field["permlevel"] = 1
		elif field["fieldname"] in COMPANY_FISCAL_SECRET_FIELDNAMES:
			field["permlevel"] = 2

	return {"Company": fields}


def install_company_fiscal_custom_fields() -> None:
	"""Create or reconcile Company fiscal fields without duplicating them."""
	fields = get_company_fiscal_custom_fields()
	fields.update(get_fel_master_and_transaction_custom_fields())
	create_custom_fields(fields, update=True)
	install_company_fiscal_permissions()


def get_fel_master_and_transaction_custom_fields() -> dict[str, list[dict[str, object]]]:
	"""Return explicit FEL fields outside Company; no fiscal values are inferred."""
	return {
		"Customer": [
			{
				"fieldname": "contanext_gt_fel_selected",
				"label": "Seleccionado para FEL",
				"fieldtype": "Check",
				"default": "0",
				"insert_after": "tax_id",
			},
			{
				"fieldname": "contanext_gt_identification_type",
				"label": "Tipo de identificación FEL",
				"fieldtype": "Select",
				"options": "\nNIT\nCUI\nCF\nEXT",
				"insert_after": "contanext_gt_fel_selected",
			},
			{
				"fieldname": "contanext_gt_taxpayer_validation",
				"label": "Validación tributaria vigente",
				"fieldtype": "Link",
				"options": "GT Taxpayer Validation",
				"read_only": 1,
				"insert_after": "contanext_gt_identification_type",
			},
			{
				"fieldname": "contanext_gt_taxpayer_validation_status",
				"label": "Estado de validación tributaria",
				"fieldtype": "Data",
				"read_only": 1,
				"insert_after": "contanext_gt_taxpayer_validation",
			},
			{
				"fieldname": "contanext_gt_taxpayer_returned_name",
				"label": "Nombre retornado por TEKRA",
				"fieldtype": "Data",
				"read_only": 1,
				"insert_after": "contanext_gt_taxpayer_validation_status",
			},
		],
		"Item": [
			{
				"fieldname": "contanext_gt_fel_item_kind",
				"label": "Clasificación FEL",
				"fieldtype": "Select",
				"options": "\nB\nS",
				"insert_after": "item_group",
			},
		],
		"Sales Invoice": _sales_document_fel_fields(),
		"POS Invoice": _sales_document_fel_fields(),
	}


def _sales_document_fel_fields() -> list[dict[str, object]]:
	return [
		{
			"fieldname": "contanext_gt_request_fel",
			"label": "Solicitar FEL",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "customer",
		},
		{
			"fieldname": "contanext_gt_fel_decision_source",
			"label": "Origen de decisión FEL",
			"fieldtype": "Select",
			"options": "\nCOMPANY\nCUSTOMER\nUSER",
			"read_only": 1,
			"insert_after": "contanext_gt_request_fel",
		},
		{
			"fieldname": "contanext_gt_fel_establishment",
			"label": "Establecimiento FEL",
			"fieldtype": "Link",
			"options": "GT FEL Establishment",
			"insert_after": "contanext_gt_fel_decision_source",
		},
		{
			"fieldname": "contanext_gt_fel_export",
			"label": "Exportación FEL",
			"fieldtype": "Check",
			"default": "0",
			"insert_after": "contanext_gt_fel_establishment",
		},
		{
			"fieldname": "contanext_gt_fel_status",
			"label": "Estado FEL",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "contanext_gt_fel_export",
		},
		{
			"fieldname": "contanext_gt_fel_operation",
			"label": "Operación FEL",
			"fieldtype": "Link",
			"options": "FEL Operation",
			"read_only": 1,
			"insert_after": "contanext_gt_fel_status",
		},
		{
			"fieldname": "contanext_gt_fel_uuid",
			"label": "UUID FEL",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "contanext_gt_fel_operation",
		},
		{
			"fieldname": "contanext_gt_fel_series",
			"label": "Serie FEL",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "contanext_gt_fel_uuid",
		},
		{
			"fieldname": "contanext_gt_fel_number",
			"label": "Número FEL",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "contanext_gt_fel_series",
		},
	]


def install_company_fiscal_permissions() -> None:
	"""Reconcile the approved Company and fiscal-field role matrix."""
	for permlevel, role_matrix in COMPANY_FISCAL_PERMISSION_MATRIX.items():
		for role, allowed_rights in role_matrix.items():
			filters = {
				"parent": "Company",
				"role": role,
				"permlevel": permlevel,
				"if_owner": 0,
			}
			if not frappe.db.exists("Custom DocPerm", filters):
				add_permission("Company", role, permlevel)

			for right in get_rights("Company"):
				update_permission_property(
					"Company",
					role,
					permlevel,
					right,
					int(right in allowed_rights),
					validate=False,
				)

	frappe.clear_cache(doctype="Company")
