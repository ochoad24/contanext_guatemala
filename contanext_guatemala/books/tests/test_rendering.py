import unittest

from contanext_guatemala.books.constants import UNAUTHORIZED_DRAFT_LABEL
from contanext_guatemala.books.rendering import (
	PaginationChanged,
	RenderFingerprint,
	assert_stable_pagination,
	draft_watermark_html,
	folio_marker,
	format_folio,
	replace_folio_marker,
	replace_folio_markers,
	build_prototype_html,
)


class TestRendering(unittest.TestCase):
	def test_folio_replacement_preserves_width(self):
		marker = folio_marker(12)
		folio = format_folio(42, 12)
		self.assertEqual(len(marker), len(folio))
		self.assertEqual(replace_folio_marker(f"<footer>{marker}</footer>", 42), f"<footer>{folio}</footer>")

	def test_pagination_change_fails_closed(self):
		with self.assertRaises(PaginationChanged):
			assert_stable_pagination(RenderFingerprint(2, "a"), RenderFingerprint(3, "b"))

	def test_draft_label_is_visible(self):
		self.assertIn(UNAUTHORIZED_DRAFT_LABEL, draft_watermark_html())

	def test_prototype_format_has_one_fixed_width_marker_per_page(self):
		html, pages = build_prototype_html(
			book_title="Libro Diario", company="Empresa GT", period="2026",
			tax_identity={"nit": "123-K"}, columns=("cuenta", "debito"),
			rows=({"cuenta": f"Cuenta {index}", "debito": index} for index in range(3)),
			emission_sha256="a" * 64, rows_per_page=2,
		)
		self.assertEqual(pages, 2)
		self.assertEqual(html.count(folio_marker()), 2)
		final = replace_folio_markers(html, 7, pages)
		self.assertIn(format_folio(7), final)
		self.assertIn(format_folio(8), final)
		self.assertIn(UNAUTHORIZED_DRAFT_LABEL, final)


if __name__ == "__main__":
	unittest.main()
