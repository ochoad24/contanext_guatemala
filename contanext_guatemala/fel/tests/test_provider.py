from unittest import TestCase
from unittest.mock import patch

from contanext_guatemala.fel.provider import (
	FEL_PROVIDER_REGISTRY,
	FELProviderNotConfigured,
	UnconfiguredFELProvider,
	get_fel_provider,
)
from contanext_guatemala.fel.tekra import TekraFELProvider


class TestFELProviderResolver(TestCase):
	def test_builtin_tekra_provider_is_registered(self):
		provider = get_fel_provider("TEKRA")

		self.assertIsInstance(provider, TekraFELProvider)

	def test_instantiates_registered_provider_after_normalizing_name(self):
		with patch.dict(
			FEL_PROVIDER_REGISTRY,
			{"registered-provider": UnconfiguredFELProvider},
			clear=True,
		):
			provider = get_fel_provider(" registered-provider ")

		self.assertIsInstance(provider, UnconfiguredFELProvider)

	def test_rejects_empty_and_unregistered_provider_names(self):
		with patch.dict(FEL_PROVIDER_REGISTRY, {}, clear=True):
			for provider_name, expected in ((None, "vacío"), ("missing", "missing")):
				with self.subTest(provider_name=provider_name), self.assertRaisesRegex(
					FELProviderNotConfigured, expected
				):
					get_fel_provider(provider_name)
