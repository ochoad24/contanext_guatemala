from __future__ import annotations

import os
from dataclasses import dataclass, field


TEKRA_SECRET_ENV_VARS = (
	"TEKRA_FEL_USER",
	"TEKRA_FEL_PASSWORD",
	"TEKRA_FEL_CLIENT",
	"TEKRA_FEL_CONTRACT",
	"TEKRA_FEL_COMPANY_ID",
)
TEKRA_ENDPOINT_ENV_VARS = {
	"SANDBOX": "TEKRA_FEL_SANDBOX_URL",
	"PRODUCTION": "TEKRA_FEL_PRODUCTION_URL",
}
TEKRA_SANDBOX_CERTIFY_SOAP_ACTION = (
	"http://apicertificacion.desa.tekra.com.gt:8080/certificacion/wsdl/CertificacionDocumento"
)
TEKRA_SANDBOX_CANCEL_SOAP_ACTION = (
	"http://apicertificacion.desa.tekra.com.gt:8080/certificacion/wsdl/AnulacionDocumento"
)


@dataclass(frozen=True, slots=True)
class TekraEnvironmentSettings:
	environment: str
	endpoint: str
	connect_timeout_seconds: int
	read_timeout_seconds: int
	max_response_bytes: int
	user: str = field(repr=False)
	password: str = field(repr=False)
	client: str = field(repr=False)
	contract: str = field(repr=False)
	certify_soap_action: str
	cancel_soap_action: str


class FELConfigurationError(ValueError):
	pass


def validate_tekra_environment(environment: str, *, environ: dict[str, str] | None = None) -> TekraEnvironmentSettings:
	values = environ if environ is not None else os.environ
	normalized_environment = environment.strip().upper()
	endpoint_variable = TEKRA_ENDPOINT_ENV_VARS.get(normalized_environment)
	if not endpoint_variable:
		raise FELConfigurationError("El ambiente TEKRA debe ser SANDBOX o PRODUCTION.")

	required = (*TEKRA_SECRET_ENV_VARS, endpoint_variable)
	missing = tuple(name for name in required if not values.get(name, "").strip())
	if missing:
		raise FELConfigurationError(
			"Faltan variables de entorno TEKRA: " + ", ".join(missing)
		)

	connect_timeout = _positive_int(values.get("TEKRA_FEL_CONNECT_TIMEOUT_SECONDS", "5"), "connect timeout")
	read_timeout = _positive_int(values.get("TEKRA_FEL_READ_TIMEOUT_SECONDS", "30"), "read timeout")
	max_response_bytes = _positive_int(values.get("TEKRA_FEL_MAX_RESPONSE_BYTES", "10485760"), "response limit")
	if normalized_environment == "SANDBOX":
		certify_soap_action = values.get(
			"TEKRA_FEL_SANDBOX_CERTIFY_SOAP_ACTION", TEKRA_SANDBOX_CERTIFY_SOAP_ACTION
		).strip()
		cancel_soap_action = values.get(
			"TEKRA_FEL_SANDBOX_CANCEL_SOAP_ACTION", TEKRA_SANDBOX_CANCEL_SOAP_ACTION
		).strip()
	else:
		action_variables = (
			"TEKRA_FEL_PRODUCTION_CERTIFY_SOAP_ACTION",
			"TEKRA_FEL_PRODUCTION_CANCEL_SOAP_ACTION",
		)
		missing_actions = tuple(name for name in action_variables if not values.get(name, "").strip())
		if missing_actions:
			raise FELConfigurationError("Faltan variables de entorno TEKRA: " + ", ".join(missing_actions))
		certify_soap_action = values[action_variables[0]].strip()
		cancel_soap_action = values[action_variables[1]].strip()
	return TekraEnvironmentSettings(
		environment=normalized_environment,
		endpoint=values[endpoint_variable].strip(),
		connect_timeout_seconds=connect_timeout,
		read_timeout_seconds=read_timeout,
		max_response_bytes=max_response_bytes,
		user=values["TEKRA_FEL_USER"].strip(),
		password=values["TEKRA_FEL_PASSWORD"].strip(),
		client=values["TEKRA_FEL_CLIENT"].strip(),
		contract=values["TEKRA_FEL_CONTRACT"].strip(),
		certify_soap_action=certify_soap_action,
		cancel_soap_action=cancel_soap_action,
	)


def _positive_int(value: str, label: str) -> int:
	try:
		parsed = int(value)
	except (TypeError, ValueError) as exc:
		raise FELConfigurationError(f"{label} debe ser un entero positivo.") from exc
	if parsed <= 0:
		raise FELConfigurationError(f"{label} debe ser un entero positivo.")
	return parsed
