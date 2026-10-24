import io
from dataclasses import dataclass


MAX_ANNEX_BYTES = 25 * 1024 * 1024
MAX_ANNEX_PAGES = 500
ACTIVE_PDF_MARKERS = (b"/JavaScript", b"/JS", b"/OpenAction", b"/AA", b"/Launch", b"/RichMedia")


@dataclass(frozen=True, slots=True)
class PDFValidation:
	sha256: str
	size_bytes: int
	page_count: int
	security_status: str


def validate_pdf(content: bytes) -> PDFValidation:
	from contanext_guatemala.books.snapshots import sha256_hex

	if not content.startswith(b"%PDF-"):
		raise ValueError("El archivo no tiene una firma PDF válida.")
	if len(content) > MAX_ANNEX_BYTES:
		raise ValueError("El anexo excede el tamaño máximo de 25 MiB.")
	if any(marker in content for marker in ACTIVE_PDF_MARKERS):
		raise ValueError("El PDF contiene acciones, scripts o contenido activo no permitido.")
	from pypdf import PdfReader

	reader = PdfReader(io.BytesIO(content), strict=True)
	if reader.is_encrypted:
		raise ValueError("Los anexos PDF cifrados no están permitidos.")
	page_count = len(reader.pages)
	if page_count < 1 or page_count > MAX_ANNEX_PAGES:
		raise ValueError("El PDF debe tener entre 1 y 500 páginas.")
	return PDFValidation(
		sha256=sha256_hex(content),
		size_bytes=len(content),
		page_count=page_count,
		security_status="Structural Checks Passed",
	)
