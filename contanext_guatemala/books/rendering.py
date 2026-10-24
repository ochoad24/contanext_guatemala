import re
from html import escape
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from contanext_guatemala.books.constants import FOLIO_MARKER_PREFIX, UNAUTHORIZED_DRAFT_LABEL


class PaginationChanged(RuntimeError):
	pass


@dataclass(frozen=True, slots=True)
class RenderFingerprint:
	page_count: int
	logical_sha256: str


def folio_marker(width: int = 12) -> str:
	if width <= len(FOLIO_MARKER_PREFIX):
		raise ValueError("El ancho del marcador no permite un folio.")
	return FOLIO_MARKER_PREFIX + ("0" * (width - len(FOLIO_MARKER_PREFIX)))


def format_folio(folio: int, width: int = 12) -> str:
	if folio < 1:
		raise ValueError("El folio debe ser positivo.")
	value = FOLIO_MARKER_PREFIX + str(folio).zfill(width - len(FOLIO_MARKER_PREFIX))
	if len(value) != width:
		raise ValueError("El folio no cabe en el marcador reservado.")
	return value


def replace_folio_marker(html: str, folio: int, width: int = 12) -> str:
	marker = folio_marker(width)
	if html.count(marker) != 1:
		raise ValueError("El documento debe contener exactamente un marcador de folio.")
	return html.replace(marker, format_folio(folio, width))


def replace_folio_markers(html: str, first_folio: int, count: int, width: int = 12) -> str:
	"""Replace one fixed-width marker per physical PDF page in document order."""
	marker = folio_marker(width)
	if count < 1 or html.count(marker) != count:
		raise ValueError("La cantidad de marcadores no coincide con las páginas reservadas.")
	for offset in range(count):
		html = html.replace(marker, format_folio(first_folio + offset, width), 1)
	return html


def assert_stable_pagination(preliminary: RenderFingerprint, final: RenderFingerprint) -> None:
	if preliminary.page_count != final.page_count:
		raise PaginationChanged(
			f"El render final cambió de {preliminary.page_count} a {final.page_count} páginas."
		)


def draft_watermark_html() -> str:
	label = re.sub(r"[^\wÁÉÍÓÚÜÑáéíóúüñ —]", "", UNAUTHORIZED_DRAFT_LABEL)
	return f'<div class="gt-book-draft-watermark">{label}</div>'


def build_prototype_html(
	*,
	book_title: str,
	company: str,
	period: str,
	tax_identity: Mapping[str, object],
	columns: Iterable[str],
	rows: Iterable[Mapping[str, object]],
	emission_sha256: str,
	authorizations: Iterable[str] = (),
	signatories: Mapping[str, object] | None = None,
	rows_per_page: int = 32,
) -> tuple[str, int]:
	"""Build a local-only, explicitly non-legal, deterministically paginated document."""
	if rows_per_page < 1:
		raise ValueError("rows_per_page debe ser positivo.")
	column_list = tuple(columns)
	row_list = list(rows)
	pages = [row_list[index : index + rows_per_page] for index in range(0, len(row_list), rows_per_page)] or [[]]
	authority_text = " · ".join(str(value) for value in authorizations) or "Sin evidencia controladora"
	signatories = signatories or {}
	signature_text = " · ".join(
		value for value in (
			f"Representante: {signatories.get('representative', '')}" if signatories.get("representative") else "",
			f"Contador: {signatories.get('accountant', '')}" if signatories.get("accountant") else "",
		) if value
	) or "Firmantes pendientes de política aprobada"
	page_html = []
	for page_number, page_rows in enumerate(pages, start=1):
		headings = "".join(f"<th>{escape(str(column))}</th>" for column in column_list)
		body = "".join(
			"<tr>" + "".join(f"<td>{escape(str(row.get(column, '')))}</td>" for column in column_list) + "</tr>"
			for row in page_rows
		)
		page_html.append(
			f'<section class="gt-book-page"><header><strong>{escape(company)}</strong>'
			f'<span>NIT {escape(str(tax_identity.get("nit", "")))}</span>'
			f'<span>{escape(book_title)} · {escape(period)}</span>'
			f'<span>{escape(authority_text)}</span></header>{draft_watermark_html()}'
			f'<table><thead><tr>{headings}</tr></thead><tbody>{body}</tbody></table>'
			f'<div class="gt-book-signatures">{escape(signature_text)}</div>'
			f'<footer><span>Emisión {escape(emission_sha256[:12])}</span>'
			f'<span>Página {page_number}/{len(pages)}</span><span>{folio_marker()}</span></footer></section>'
		)
	css = """
		@page { size: letter landscape; margin: 8mm; }
		* { box-sizing: border-box; }
		body { margin: 0; font-family: 'DejaVu Sans', sans-serif; font-size: 8px; color: #111; }
		.gt-book-page { position: relative; min-height: 190mm; page-break-after: always; }
		.gt-book-page:last-child { page-break-after: auto; }
		header, footer { display: flex; justify-content: space-between; gap: 8px; }
		header { border-bottom: 1px solid #333; padding-bottom: 4px; }
		footer { position: absolute; bottom: 0; width: 100%; border-top: 1px solid #333; padding-top: 4px; }
		.gt-book-signatures { position: absolute; bottom: 10mm; width: 100%; text-align: center; }
		table { border-collapse: collapse; margin-top: 8px; width: 100%; table-layout: fixed; }
		th, td { border: 1px solid #aaa; padding: 2px; overflow-wrap: anywhere; }
		.gt-book-draft-watermark { color: #9b1c1c; font-size: 15px; font-weight: bold; text-align: center; padding: 5px; }
	"""
	return f"<!doctype html><html lang='es'><head><meta charset='utf-8'><style>{css}</style></head><body>{''.join(page_html)}</body></html>", len(pages)
