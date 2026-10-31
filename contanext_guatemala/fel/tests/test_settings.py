from unittest import TestCase

from contanext_guatemala.fel.settings import FELConfigurationError, validate_tekra_environment


BASE_ENV = {
	"TEKRA_FEL_USER": "user",
	"TEKRA_FEL_PASSWORD": "secret",
	"TEKRA_FEL_CLIENT": "client",
	"TEKRA_FEL_CONTRACT": "contract",
	"TEKRA_FEL_COMPANY_ID": "company-id",
	"TEKRA_FEL_SANDBOX_URL": "https://sandbox.invalid/soap",
	"TEKRA_FEL_PRODUCTION_URL": "https://production.invalid/soap",
}


class TestTekraEnvironmentSettings(TestCase):
	def test_resolves_environment_specific_endpoint_and_safe_defaults(self):
		settings = validate_tekra_environment("sandbox", environ=BASE_ENV)

		self.assertEqual(settings.environment, "SANDBOX")
		self.assertEqual(settings.endpoint, BASE_ENV["TEKRA_FEL_SANDBOX_URL"])
		self.assertEqual(settings.connect_timeout_seconds, 5)
		self.assertEqual(settings.read_timeout_seconds, 30)
		self.assertEqual(settings.max_response_bytes, 10485760)
		self.assertNotIn("secret", repr(settings))

	def test_production_never_falls_back_to_sandbox_endpoint(self):
		environ = {**BASE_ENV, "TEKRA_FEL_PRODUCTION_URL": ""}
		with self.assertRaisesRegex(FELConfigurationError, "TEKRA_FEL_PRODUCTION_URL"):
			validate_tekra_environment("PRODUCTION", environ=environ)

	def test_production_requires_explicit_soap_actions(self):
		environ = {
			**BASE_ENV,
			"TEKRA_FEL_PRODUCTION_CERTIFY_SOAP_ACTION": "",
			"TEKRA_FEL_PRODUCTION_CANCEL_SOAP_ACTION": "",
		}
		with self.assertRaisesRegex(FELConfigurationError, "PRODUCTION_CERTIFY_SOAP_ACTION"):
			validate_tekra_environment("PRODUCTION", environ=environ)

	def test_reports_missing_secrets_by_name_without_values(self):
		environ = {**BASE_ENV, "TEKRA_FEL_PASSWORD": ""}
		with self.assertRaisesRegex(FELConfigurationError, "TEKRA_FEL_PASSWORD") as error:
			validate_tekra_environment("SANDBOX", environ=environ)

		self.assertNotIn("secret", str(error.exception))

	def test_rejects_non_positive_timeouts(self):
		with self.assertRaisesRegex(FELConfigurationError, "entero positivo"):
			validate_tekra_environment(
				"SANDBOX",
				environ={**BASE_ENV, "TEKRA_FEL_CONNECT_TIMEOUT_SECONDS": "0"},
			)

		with self.assertRaisesRegex(FELConfigurationError, "entero positivo"):
			validate_tekra_environment(
				"SANDBOX",
				environ={**BASE_ENV, "TEKRA_FEL_MAX_RESPONSE_BYTES": "0"},
			)
