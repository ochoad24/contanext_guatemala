import frappe


def after_install() -> None:
	configure_site()


def configure_site() -> dict[str, str]:
	"""Apply safe locale defaults without creating accounting masters.

	Company and chart-of-accounts creation remain explicit ERPNext setup steps,
	because silently creating them is unsafe for an existing tenant.
	"""
	settings = frappe.get_single("System Settings")
	settings.country = "Guatemala"
	settings.time_zone = "America/Guatemala"
	settings.language = "es"
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
