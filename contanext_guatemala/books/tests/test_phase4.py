import unittest
from datetime import date
from decimal import Decimal
from itertools import repeat
from types import SimpleNamespace

from contanext_guatemala.books.inventory import collapse_sle_rows, reconcile_inventory
from contanext_guatemala.books.physical_counts import parse_physical_count, sha256_hex
from contanext_guatemala.books.types import BookScope


SCOPE = BookScope("Empresa GT", date(2026, 1, 1), date(2026, 12, 31), "2026")


def balance(item="ITEM-1", warehouse="Bodega - GT", quantity="10", value="100"):
	return {
		"item_code": item,
		"item_name": item,
		"item_group": "Productos",
		"warehouse": warehouse,
		"uom": "Unidad",
		"book_quantity": Decimal(quantity),
		"valuation_rate": Decimal("10"),
		"stock_value": Decimal(value),
	}


MAPPING = {
	"scope_type": "WAREHOUSE",
	"warehouse": "Bodega - GT",
	"item_code": None,
	"item_group": None,
	"inventory_account": "Inventarios - GT",
	"category": "MERCADERIA",
}


class TestPhysicalCount(unittest.TestCase):
	def test_csv_template_preserves_decimal_and_hash(self):
		content = (
			"item_code,warehouse,uom,counted_quantity,note\n"
			"ITEM-1,Bodega - GT,Unidad,10.250,Conteo firmado\n"
		).encode()
		rows = parse_physical_count(content, "conteo.csv")
		self.assertEqual(rows[0].counted_quantity, Decimal("10.250"))
		self.assertEqual(rows[0].status, "Accepted")
		self.assertEqual(len(sha256_hex(content)), 64)

	def test_csv_rejects_invalid_quantity(self):
		content = b"item_code,warehouse,uom,counted_quantity\nITEM-1,Bodega - GT,Unidad,no\n"
		rows = parse_physical_count(content, "conteo.csv")
		self.assertEqual(rows[0].status, "Rejected")


class TestInventoryReconciliation(unittest.TestCase):
	def test_stock_physical_and_gl_reconcile_exactly(self):
		result = reconcile_inventory(
			SCOPE,
			balances=[balance()],
			mappings=[MAPPING],
			physical_counts={("ITEM-1", "Bodega - GT"): Decimal("10")},
			gl_balances={"Inventarios - GT": Decimal("100")},
		)
		self.assertTrue(result.reconciled)
		self.assertEqual(result.value_difference, 0)
		self.assertEqual(result.rows[0]["row_type"], "SUMMARY")
		self.assertEqual(result.rows[-1]["row_type"], "DECLARATION")

	def test_mapping_overlap_and_differences_are_blocking(self):
		second = MAPPING | {"scope_type": "ITEM", "warehouse": None, "item_code": "ITEM-1"}
		result = reconcile_inventory(
			SCOPE,
			balances=[balance(quantity="-1")],
			mappings=[MAPPING, second],
			physical_counts={("ITEM-1", "Bodega - GT"): Decimal("0")},
			gl_balances={"Inventarios - GT": Decimal("0")},
		)
		self.assertFalse(result.reconciled)
		self.assertEqual(result.ambiguous, 1)
		self.assertEqual(result.negative, 1)
		self.assertEqual(result.physical_differences, 1)

	def test_one_million_sle_rows_collapse_without_materializing_source(self):
		row = SimpleNamespace(
			item_code="ITEM-1",
			warehouse="Bodega - GT",
			item_name="Artículo",
			item_group="Productos",
			stock_uom="Unidad",
			qty_after_transaction=10,
			valuation_rate=10,
			stock_value=100,
		)
		result = list(collapse_sle_rows(repeat(row, 1_000_000)))
		self.assertEqual(len(result), 1)
		self.assertEqual(result[0]["stock_value"], Decimal("100"))


if __name__ == "__main__":
	unittest.main()
