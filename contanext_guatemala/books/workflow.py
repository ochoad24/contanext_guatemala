from dataclasses import dataclass
from typing import AbstractSet

from contanext_guatemala.books.constants import BookRunStatus


class InvalidTransition(ValueError):
	pass


@dataclass(frozen=True, slots=True)
class TransitionContext:
	actor: str
	prepared_by: str | None = None
	reviewed_by: str | None = None
	roles: AbstractSet[str] = frozenset()
	idempotency_key: str | None = None
	preflight_passed: bool = False


TRANSITIONS: dict[BookRunStatus, frozenset[BookRunStatus]] = {
	BookRunStatus.DRAFT: frozenset({BookRunStatus.QUEUED}),
	BookRunStatus.QUEUED: frozenset({BookRunStatus.GENERATED, BookRunStatus.VALIDATION_FAILED}),
	BookRunStatus.GENERATED: frozenset(
		{BookRunStatus.VALIDATION_FAILED, BookRunStatus.READY_FOR_REVIEW}
	),
	BookRunStatus.VALIDATION_FAILED: frozenset({BookRunStatus.QUEUED}),
	BookRunStatus.READY_FOR_REVIEW: frozenset({BookRunStatus.APPROVED, BookRunStatus.REJECTED}),
	BookRunStatus.REJECTED: frozenset({BookRunStatus.QUEUED}),
	BookRunStatus.APPROVED: frozenset({BookRunStatus.SEALING}),
	BookRunStatus.SEALING: frozenset(
		{BookRunStatus.AWAITING_PRINT_CONFIRMATION, BookRunStatus.SEAL_FAILED}
	),
	BookRunStatus.AWAITING_PRINT_CONFIRMATION: frozenset(
		{BookRunStatus.SEALED, BookRunStatus.PRINT_EXCEPTION}
	),
	BookRunStatus.PRINT_EXCEPTION: frozenset(
		{BookRunStatus.AWAITING_PRINT_CONFIRMATION, BookRunStatus.SEALING}
	),
	BookRunStatus.SEAL_FAILED: frozenset({BookRunStatus.SEALING}),
	BookRunStatus.SEALED: frozenset({BookRunStatus.SUPERSEDED}),
	BookRunStatus.SUPERSEDED: frozenset(),
}


def validate_transition(
	current: BookRunStatus | str,
	target: BookRunStatus | str,
	context: TransitionContext,
) -> None:
	current_status = BookRunStatus(current)
	target_status = BookRunStatus(target)
	if target_status not in TRANSITIONS[current_status]:
		raise InvalidTransition(f"Transición no permitida: {current_status} → {target_status}")
	if not context.actor:
		raise InvalidTransition("Toda transición requiere un actor.")
	if target_status == BookRunStatus.READY_FOR_REVIEW and context.actor != context.prepared_by:
		raise InvalidTransition("Solo el preparador puede enviar la emisión a revisión.")
	if target_status in {BookRunStatus.APPROVED, BookRunStatus.REJECTED}:
		if context.actor == context.prepared_by:
			raise InvalidTransition("El preparador no puede revisar su propia emisión.")
	if target_status == BookRunStatus.REJECTED and "GT Books Reviewer" not in context.roles:
		raise InvalidTransition("El rechazo requiere el rol GT Books Reviewer.")
	if target_status == BookRunStatus.APPROVED and not context.preflight_passed:
		raise InvalidTransition("No se puede aprobar con preflight bloqueante.")
	if target_status == BookRunStatus.APPROVED:
		if not context.reviewed_by:
			raise InvalidTransition("La emisión debe contar con revisión previa.")
		if context.actor in {context.prepared_by, context.reviewed_by}:
			raise InvalidTransition("Preparador, revisor y aprobador deben ser distintos.")
		if "GT Books Manager" not in context.roles:
			raise InvalidTransition("La aprobación requiere el rol GT Books Manager.")
	if target_status == BookRunStatus.SEALING:
		if "GT Books Manager" not in context.roles:
			raise InvalidTransition("El sellado requiere el rol GT Books Manager.")
		if not context.idempotency_key:
			raise InvalidTransition("El sellado requiere una clave de idempotencia.")
	if target_status == BookRunStatus.SEALED and "GT Books Manager" not in context.roles:
		raise InvalidTransition("La confirmación física requiere el rol GT Books Manager.")
	if target_status == BookRunStatus.SUPERSEDED and "GT Books Manager" not in context.roles:
		raise InvalidTransition("La sustitución requiere el rol GT Books Manager.")
