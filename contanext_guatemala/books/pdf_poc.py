import hashlib
import os
import subprocess
from pathlib import Path

from contanext_guatemala.books.rendering import RenderFingerprint


def chromium_executable() -> str:
	return os.environ.get("CHROMIUM_PATH", "/usr/lib/chromium/chromium-headless-shell")


def render_html(html_file: Path, pdf_file: Path, executable: str | None = None) -> RenderFingerprint:
	"""Render local-only HTML and fingerprint its logical PDF content."""
	binary = executable or chromium_executable()
	if not Path(binary).is_file():
		raise FileNotFoundError(f"Chromium fijado no existe: {binary}")
	result = subprocess.run(
		[
			binary,
			"--headless",
			"--no-sandbox",
			"--disable-gpu",
			"--disable-software-rasterizer",
			"--no-pdf-header-footer",
			f"--print-to-pdf={pdf_file}",
			html_file.resolve().as_uri(),
		],
		check=False,
		capture_output=True,
		text=True,
		timeout=60,
	)
	if result.returncode or not pdf_file.is_file():
		raise RuntimeError(f"Chromium no pudo producir el PDF: {result.stderr[-1000:]}")
	return fingerprint_pdf(pdf_file)


def fingerprint_pdf(pdf_file: Path) -> RenderFingerprint:
	from pypdf import PdfReader

	reader = PdfReader(str(pdf_file))
	logical_content = "\n\f\n".join((page.extract_text() or "") for page in reader.pages)
	return RenderFingerprint(
		page_count=len(reader.pages),
		logical_sha256=hashlib.sha256(logical_content.encode("utf-8")).hexdigest(),
	)
