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


class FELProviderNotConfigured(RuntimeError):
	pass


class UnconfiguredFELProvider(FELProvider):
	"""Fail closed. This provider never simulates a valid fiscal operation."""

	def certify(self, request: CertificationRequest) -> CertificationResult:
		raise FELProviderNotConfigured("No hay un certificador FEL autorizado configurado.")

	def cancel(self, uuid: str, reason: str) -> CertificationResult:
		raise FELProviderNotConfigured("No hay un certificador FEL autorizado configurado.")

	def query(self, uuid: str) -> CertificationResult:
		raise FELProviderNotConfigured("No hay un certificador FEL autorizado configurado.")
