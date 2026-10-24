from __future__ import annotations

from abc import ABC, abstractmethod

from contanext_guatemala.fel.types import CertificationRequest, CertificationResult


class FELProvider(ABC):
	"""Contract implemented by adapters for SAT-authorized certifiers."""

	@abstractmethod
	def certify(self, request: CertificationRequest) -> CertificationResult:
		raise NotImplementedError

	@abstractmethod
	def cancel(self, uuid: str, reason: str) -> CertificationResult:
		raise NotImplementedError

	@abstractmethod
	def query(self, uuid: str) -> CertificationResult:
		raise NotImplementedError
