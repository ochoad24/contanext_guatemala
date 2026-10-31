import frappe

from contanext_guatemala.fiscal.setup import install_company_fiscal_custom_fields


def after_install() -> None:
	configure_site()
	configure_branding()
	install_book_roles()
	install_fel_roles()
	install_company_fiscal_custom_fields()


def after_migrate() -> None:
	configure_branding()
	install_book_roles()
	install_fel_roles()
	install_company_fiscal_custom_fields()


def configure_branding() -> None:
	"""Keep the product name shown by Frappe consistent on existing sites."""
	frappe.db.set_single_value("System Settings", "app_name", "ContaNext")
	frappe.db.set_single_value("Website Settings", "app_name", "ContaNext")


def configure_site() -> dict[str, str]:
	"""Apply safe locale defaults without creating accounting masters.

	Company and chart-of-accounts creation remain explicit ERPNext setup steps,
	because silently creating them is unsafe for an existing tenant.
	"""
	settings = frappe.get_single("System Settings")
	settings.country = "Guatemala"
	settings.time_zone = "America/Guatemala"
	settings.language = "es"
	settings.app_name = "ContaNext"
	settings.save(ignore_permissions=True)

	frappe.db.set_default("country", "Guatemala")
	frappe.db.set_default("currency", "GTQ")
	frappe.db.set_default("lang", "es")
	frappe.db.commit()
	return {
		"country": "Guatemala",
		"currency": "GTQ",
		"language": "es",
		"time_zone": "America/Guatemala",
	}


BOOK_ROLES = ("GT Books User", "GT Books Reviewer", "GT Books Manager", "GT Books Auditor")
FEL_ROLES = (
	"GT FEL User",
	"GT FEL Operator",
	"GT FEL Manager",
	"GT FEL Auditor",
	"GT FEL Billing Manager",
	"GT FEL Billing Auditor",
)


def install_book_roles() -> None:
	"""Create operational roles without assigning them to any user."""
	for role_name in BOOK_ROLES:
		if frappe.db.exists("Role", role_name):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 1,
				"is_custom": 1,
			}
		).insert(ignore_permissions=True)


def install_fel_roles() -> None:
	"""Create FEL roles idempotently without granting them to users."""
	for role_name in FEL_ROLES:
		if frappe.db.exists("Role", role_name):
			continue
		frappe.get_doc(
			{
				"doctype": "Role",
				"role_name": role_name,
				"desk_access": 1,
				"is_custom": 1,
			}
		).insert(ignore_permissions=True)
