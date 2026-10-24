import frappe
from frappe import _

from contanext_guatemala.books.catalog import diagnose_company_catalog


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		frappe.throw(_("La empresa es obligatoria"))
	frappe.get_doc("Company", filters.company).check_permission("read")
	findings = diagnose_company_catalog(filters.company)
	return get_columns(), [
		{
			"code": finding.code,
			"severity": finding.severity,
			"account": finding.account,
			"message": finding.message,
		}
		for finding in findings
	]


def get_columns():
	return [
		{"fieldname": "code", "fieldtype": "Data", "label": _("Control"), "width": 210},
		{"fieldname": "severity", "fieldtype": "Data", "label": _("Severidad"), "width": 100},
		{
			"fieldname": "account",
			"fieldtype": "Data",
			"label": _("Cuenta"),
			"width": 260,
		},
		{"fieldname": "message", "fieldtype": "Data", "label": _("Mensaje"), "width": 420},
	]
