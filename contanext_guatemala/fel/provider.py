from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from contanext_guatemala.fel.types import (
	CancellationRequest,
	CertificationRequest,
	CertificationResult,
	ContributorQueryRequest,
	ContributorQueryResult,
	ReconciliationRequest,
)


FEL_PROVIDER_REGISTRY: dict[str, type["FELProvider"]] = {}


def is_fel_provider_registered(provider_name: str | None) -> bool:
	_load_builtin_providers()
	return bool(provider_name and provider_name.strip() in FEL_PROVIDER_REGISTRY)


def get_fel_provider(provider_name: str | None, *, configuration: Any = None) -> "FELProvider":
	_load_builtin_providers()
	name = provider_name.strip() if provider_name else ""
	provider_type = FEL_PROVIDER_REGISTRY.get(name)
	if provider_type is None:
		raise FELProviderNotConfigured(f"El adaptador FEL {name or '[vacío]'} no está registrado.")
	return provider_type.from_configuration(configuration)


class FELProvider(ABC):
	"""Transport-neutral contract implemented by authorized certifier adapters."""

	@classmethod
	def from_configuration(cls, configuration: Any = None) -> "FELProvider":
		return cls()

	@abstractmethod
	def certify(self, request: CertificationRequest) -> CertificationResult:
		raise NotImplementedError

	@abstractmethod
	def cancel(self, request: CancellationRequest) -> CertificationResult:
		raise NotImplementedError

	@abstractmethod
	def reconcile(self, request: ReconciliationRequest) -> CertificationResult:
		raise NotImplementedError

	@abstractmethod
	def query_contributor(self, request: ContributorQueryRequest) -> ContributorQueryResult:
		raise NotImplementedError


class FELProviderError(RuntimeError):
	pass


class FELProviderNotConfigured(FELProviderError):
	pass


class FELProviderPermanentError(FELProviderError):
	pass


class FELProviderTransientError(FELProviderError):
	pass


class FELProviderUncertainError(FELProviderError):
	"""The provider may have accepted the request; callers must reconcile first."""


class UnconfiguredFELProvider(FELProvider):
	def _raise(self):
		raise FELProviderNotConfigured("No hay un certificador FEL autorizado configurado.")

	def certify(self, request: CertificationRequest) -> CertificationResult:
		self._raise()

	def cancel(self, request: CancellationRequest) -> CertificationResult:
		self._raise()

	def reconcile(self, request: ReconciliationRequest) -> CertificationResult:
		self._raise()

	def query_contributor(self, request: ContributorQueryRequest) -> ContributorQueryResult:
		self._raise()


def _load_builtin_providers() -> None:
	if "TEKRA" not in FEL_PROVIDER_REGISTRY:
		from contanext_guatemala.fel.tekra import TekraFELProvider

		FEL_PROVIDER_REGISTRY["TEKRA"] = TekraFELProvider
