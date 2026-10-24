import frappe
from frappe.utils import getdate

from contanext_guatemala.books.inventory import load_physical_counts, reconcile_inventory
from contanext_guatemala.books.types import BookScope


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.book_run:
		frappe.throw("Seleccione una emisión de Inventarios.")
	doc = frappe.get_doc("GT Accounting Book Run", filters.book_run)
	doc.check_permission("read")
	if doc.book_type != "INVENTORY":
		frappe.throw("La emisión seleccionada no corresponde al Libro de Inventarios.")
	scope = BookScope(
		company=doc.company,
		period_from=getdate(doc.period_from),
		period_to=getdate(doc.period_to),
		fiscal_year=doc.fiscal_year,
		finance_book=doc.finance_book or None,
		currency=doc.currency,
	)
	counts = load_physical_counts(doc.physical_count_import) if doc.physical_count_import else {}
	result = reconcile_inventory(scope, physical_counts=counts)
	return _columns(), list(result.rows)


def _columns():
	return [
		{"fieldname": "row_type", "label": "Tipo", "fieldtype": "Data", "width": 150},
		{"fieldname": "item_code", "label": "Artículo", "fieldtype": "Link", "options": "Item", "width": 140},
		{"fieldname": "item_name", "label": "Nombre", "fieldtype": "Data", "width": 180},
		{"fieldname": "warehouse", "label": "Bodega", "fieldtype": "Link", "options": "Warehouse", "width": 160},
		{"fieldname": "uom", "label": "Unidad", "fieldtype": "Link", "options": "UOM", "width": 90},
		{"fieldname": "book_quantity", "label": "Cantidad libro", "fieldtype": "Float", "width": 120},
		{"fieldname": "counted_quantity", "label": "Cantidad física", "fieldtype": "Float", "width": 120},
		{"fieldname": "quantity_difference", "label": "Diferencia cantidad", "fieldtype": "Float", "width": 130},
		{"fieldname": "valuation_rate", "label": "Costo unitario", "fieldtype": "Currency", "width": 120},
		{"fieldname": "stock_value", "label": "Valor Stock", "fieldtype": "Currency", "width": 120},
		{"fieldname": "inventory_account", "label": "Cuenta GL", "fieldtype": "Link", "options": "Account", "width": 180},
		{"fieldname": "gl_value", "label": "Valor GL", "fieldtype": "Currency", "width": 120},
		{"fieldname": "value_difference", "label": "Diferencia valor", "fieldtype": "Currency", "width": 130},
		{"fieldname": "cause", "label": "Causa", "fieldtype": "Data", "width": 220},
	]
