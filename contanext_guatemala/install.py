import frappe


def after_install() -> None:
	configure_site()
	configure_branding()


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
