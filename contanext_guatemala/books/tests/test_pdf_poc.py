import tempfile
import unittest
from pathlib import Path

from contanext_guatemala.books.pdf_poc import chromium_executable, render_html
from contanext_guatemala.books.rendering import assert_stable_pagination, folio_marker, replace_folio_marker


class TestChromiumPdfPoc(unittest.TestCase):
	@unittest.skipUnless(Path(chromium_executable()).is_file(), "Chromium fijado no está disponible")
	def test_repeated_and_two_pass_render_preserve_logical_content_and_pages(self):
		with tempfile.TemporaryDirectory() as directory:
			root = Path(directory)
			marker = folio_marker()
			html = f"""<!doctype html><html lang=\"es\"><meta charset=\"utf-8\">
			<style>@page {{ size: Letter; margin: 15mm; }} body {{ font-family: sans-serif; }}</style>
			<body><h1>Libro Diario</h1><p>Prueba reproducible en GTQ</p><footer>{marker}</footer></body></html>"""
			preliminary_html = root / "preliminary.html"
			preliminary_html.write_text(html, encoding="utf-8")
			first = render_html(preliminary_html, root / "first.pdf")
			second = render_html(preliminary_html, root / "second.pdf")
			self.assertEqual(first, second)

			final_html = root / "final.html"
			final_html.write_text(replace_folio_marker(html, 1), encoding="utf-8")
			final = render_html(final_html, root / "final.pdf")
			assert_stable_pagination(first, final)


if __name__ == "__main__":
	unittest.main()
