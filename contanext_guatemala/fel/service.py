from contanext_guatemala.fel.provider import FELProvider, UnconfiguredFELProvider
from contanext_guatemala.fel.types import CertificationRequest, CertificationResult


class FELService:
	def __init__(self, provider: FELProvider | None = None) -> None:
		self.provider = provider or UnconfiguredFELProvider()

	def certify(self, request: CertificationRequest) -> CertificationResult:
		if not request.xml.strip():
			raise ValueError("El XML del DTE no puede estar vacío.")
		return self.provider.certify(request)

	def cancel(self, uuid: str, reason: str) -> CertificationResult:
		if not uuid.strip() or not reason.strip():
			raise ValueError("UUID y motivo son obligatorios para anular.")
		return self.provider.cancel(uuid, reason)

	def query(self, uuid: str) -> CertificationResult:
		if not uuid.strip():
			raise ValueError("UUID es obligatorio para consultar.")
		return self.provider.query(uuid)
