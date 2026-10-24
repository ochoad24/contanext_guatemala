import gzip
import hashlib
import io
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from contanext_guatemala.books.constants import SNAPSHOT_SCHEMA, SNAPSHOT_VERSION


@dataclass(frozen=True, slots=True)
class SnapshotPart:
	index: int
	row_count: int
	content: bytes
	sha256: str


def _canonical_decimal(value: Decimal) -> str:
	if not value.is_finite():
		raise ValueError("El snapshot no admite decimales no finitos.")
	normalized = format(value, "f")
	if "." in normalized:
		normalized = normalized.rstrip("0").rstrip(".")
	return "0" if Decimal(normalized) == 0 else normalized


def canonical_value(value: Any) -> Any:
	if isinstance(value, Decimal):
		return _canonical_decimal(value)
	if isinstance(value, datetime):
		if value.tzinfo is None:
			raise ValueError("Los datetime del snapshot deben incluir zona horaria.")
		return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")
	if isinstance(value, date):
		return value.isoformat()
	if isinstance(value, Mapping):
		return {
			str(key): canonical_value(item)
			for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
		}
	if isinstance(value, (list, tuple)):
		return [canonical_value(item) for item in value]
	if value is None or isinstance(value, (str, int, bool)):
		return value
	if isinstance(value, float):
		raise TypeError("Use Decimal en lugar de float para datos contables.")
	raise TypeError(f"Tipo no canónico: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
	return json.dumps(
		canonical_value(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True
	).encode("utf-8")


def sha256_hex(value: bytes) -> str:
	return hashlib.sha256(value).hexdigest()


def _compress_deterministically(content: bytes) -> bytes:
	buffer = io.BytesIO()
	with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as compressed:
		compressed.write(content)
	return buffer.getvalue()


def build_snapshot_parts(rows: Iterable[Mapping[str, Any]], max_rows: int = 10_000) -> list[SnapshotPart]:
	return list(iter_snapshot_parts(rows, max_rows=max_rows))


def iter_snapshot_parts(
	rows: Iterable[Mapping[str, Any]], max_rows: int = 10_000
) -> Iterable[SnapshotPart]:
	if max_rows < 1:
		raise ValueError("max_rows debe ser positivo.")
	batch: list[bytes] = []
	index = 1
	for row in rows:
		batch.append(canonical_json(row) + b"\n")
		if len(batch) == max_rows:
			yield _make_part(index, batch)
			index += 1
			batch = []
	if batch:
		yield _make_part(index, batch)


def iter_snapshot_rows(parts: Iterable[SnapshotPart]) -> Iterable[dict[str, Any]]:
	for part in sorted(parts, key=lambda item: item.index):
		for line in gzip.decompress(part.content).splitlines():
			if line:
				yield json.loads(line)


def _make_part(index: int, rows: list[bytes]) -> SnapshotPart:
	content = _compress_deterministically(b"".join(rows))
	return SnapshotPart(index=index, row_count=len(rows), content=content, sha256=sha256_hex(content))


def build_manifest(parts: Iterable[SnapshotPart], metadata: Mapping[str, Any]) -> dict[str, Any]:
	part_list = list(parts)
	manifest = {
		"schema": SNAPSHOT_SCHEMA,
		"version": SNAPSHOT_VERSION,
		"metadata": canonical_value(metadata),
		"row_count": sum(part.row_count for part in part_list),
		"parts": [
			{"index": part.index, "row_count": part.row_count, "sha256": part.sha256}
			for part in part_list
		],
	}
	manifest["root_sha256"] = sha256_hex(canonical_json(manifest))
	return manifest


def verify_manifest(manifest: Mapping[str, Any]) -> bool:
	"""Verify a snapshot manifest without trusting its database record."""
	try:
		payload = dict(manifest)
		expected = payload.pop("root_sha256", None)
		if (
			not expected
			or payload.get("schema") != SNAPSHOT_SCHEMA
			or payload.get("version") != SNAPSHOT_VERSION
		):
			return False
		parts = payload.get("parts")
		if not isinstance(payload.get("metadata"), Mapping) or not isinstance(parts, list):
			return False
		if any(
			not isinstance(part, Mapping)
			or not isinstance(part.get("index"), int)
			or not isinstance(part.get("row_count"), int)
			or part["row_count"] < 0
			or not _is_sha256(part.get("sha256"))
			for part in parts
		):
			return False
		if payload.get("row_count") != sum(part["row_count"] for part in parts):
			return False
		indexes = [part["index"] for part in parts]
		if indexes != list(range(1, len(parts) + 1)):
			return False
		return expected == sha256_hex(canonical_json(payload))
	except (TypeError, ValueError):
		return False


def _is_sha256(value: Any) -> bool:
	return (
		isinstance(value, str)
		and len(value) == 64
		and all(character in "0123456789abcdef" for character in value)
	)


def emission_sha256(snapshot_manifest: Mapping[str, Any], sealable_parameters: Mapping[str, Any]) -> str:
	return sha256_hex(canonical_json({"snapshot": snapshot_manifest, "parameters": sealable_parameters}))
