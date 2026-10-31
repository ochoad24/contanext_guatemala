from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
	from contanext_guatemala.fel.service import FELService

__all__ = ["FELService"]


def __getattr__(name: str) -> Any:
	"""Keep the public service export without importing Company dependencies eagerly."""
	if name == "FELService":
		from contanext_guatemala.fel.service import FELService

		return FELService
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
