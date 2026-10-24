from collections.abc import Mapping
from typing import Any

from contanext_guatemala.books.snapshots import canonical_json, canonical_value, sha256_hex


SEAL_MANIFEST_SCHEMA = "contanext.gt.accounting-book.seal-manifest"
SEAL_MANIFEST_VERSION = 1


def build_seal_manifest(
	*,
	book_run: str,
	emission_sha256: str,
	pdf_sha256: str,
	page_count: int,
	allocation: Mapping[str, Any],
	artifacts: list[Mapping[str, Any]],
	renderer: Mapping[str, Any],
) -> dict[str, Any]:
	payload = {
		"schema": SEAL_MANIFEST_SCHEMA,
		"version": SEAL_MANIFEST_VERSION,
		"book_run": book_run,
		"emission_sha256": emission_sha256,
		"pdf_sha256": pdf_sha256,
		"page_count": page_count,
		"allocation": canonical_value(allocation),
		"artifacts": canonical_value(artifacts),
		"renderer": canonical_value(renderer),
	}
	payload["manifest_sha256"] = sha256_hex(canonical_json(payload))
	return payload


def verify_seal_manifest(manifest: Mapping[str, Any]) -> bool:
	payload = dict(manifest)
	expected = payload.pop("manifest_sha256", None)
	return (
		payload.get("schema") == SEAL_MANIFEST_SCHEMA
		and payload.get("version") == SEAL_MANIFEST_VERSION
		and isinstance(payload.get("artifacts"), list)
		and bool(expected)
		and expected == sha256_hex(canonical_json(payload))
	)


def verify_seal_bundle(manifest: Mapping[str, Any], contents_by_url: Mapping[str, bytes]) -> bool:
	"""Independently verify the canonical manifest and every referenced artifact supplied."""
	if not verify_seal_manifest(manifest):
		return False
	for artifact in manifest.get("artifacts", []):
		file_url = artifact.get("file_url")
		content = contents_by_url.get(file_url)
		if content is None or sha256_hex(content) != artifact.get("sha256"):
			return False
	pdf_artifacts = [item for item in manifest.get("artifacts", []) if item.get("type") == "SEALED_PDF"]
	return len(pdf_artifacts) == 1 and pdf_artifacts[0].get("sha256") == manifest.get("pdf_sha256")
