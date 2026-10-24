import frappe
from frappe import _

from contanext_guatemala.books.migration import assess_existing_company


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		frappe.throw(_("La empresa es obligatoria"))
	assessment = assess_existing_company(filters.company)
	rows = [
		{
			"code": check["code"],
			"severity": check["severity"],
			"status": check["status"],
			"message": check["message"],
			"assessment_sha256": assessment["assessment_sha256"],
		}
		for check in assessment["checks"]
	]
	return get_columns(), rows


def get_columns():
	return [
		{"fieldname": "code", "fieldtype": "Data", "label": _("Control"), "width": 210},
		{"fieldname": "severity", "fieldtype": "Data", "label": _("Severidad"), "width": 100},
		{"fieldname": "status", "fieldtype": "Data", "label": _("Estado"), "width": 90},
		{"fieldname": "message", "fieldtype": "Data", "label": _("Resultado"), "width": 520},
		{"fieldname": "assessment_sha256", "fieldtype": "Data", "label": _("SHA-256"), "width": 220},
	]
