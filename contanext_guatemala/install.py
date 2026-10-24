from __future__ import annotations

import frappe


def after_install() -> None:
	"""Apply safe site-wide defaults; company accounting remains an explicit setup step."""
	frappe.db.set_default("country", "Guatemala")
	frappe.db.set_default("currency", "GTQ")
	frappe.db.set_default("lang", "es")
	frappe.db.set_single_value("System Settings", "country", "Guatemala")
	frappe.db.set_single_value("System Settings", "time_zone", "America/Guatemala")
	frappe.db.set_single_value("System Settings", "language", "es")
