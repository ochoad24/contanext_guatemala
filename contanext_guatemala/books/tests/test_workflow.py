import unittest

from contanext_guatemala.books.constants import BookRunStatus
from contanext_guatemala.books.workflow import InvalidTransition, TransitionContext, validate_transition


class TestWorkflow(unittest.TestCase):
	def test_happy_path_enforces_separation_and_idempotency(self):
		validate_transition(
			BookRunStatus.GENERATED,
			BookRunStatus.READY_FOR_REVIEW,
			TransitionContext(actor="preparer@example.com", prepared_by="preparer@example.com"),
		)
		validate_transition(
			BookRunStatus.SEALING,
			BookRunStatus.AWAITING_PRINT_CONFIRMATION,
			TransitionContext(actor="worker@example.com"),
		)
		validate_transition(
			BookRunStatus.AWAITING_PRINT_CONFIRMATION,
			BookRunStatus.SEALED,
			TransitionContext(actor="manager@example.com", roles=frozenset({"GT Books Manager"})),
		)

	def test_pdf_generation_does_not_equal_physical_confirmation(self):
		with self.assertRaises(InvalidTransition):
			validate_transition(
				BookRunStatus.SEALING,
				BookRunStatus.SEALED,
				TransitionContext(actor="manager@example.com", roles=frozenset({"GT Books Manager"})),
			)
		validate_transition(
			BookRunStatus.READY_FOR_REVIEW,
			BookRunStatus.APPROVED,
			TransitionContext(
				actor="manager@example.com",
				prepared_by="preparer@example.com",
				reviewed_by="reviewer@example.com",
				roles=frozenset({"GT Books Manager"}),
				preflight_passed=True,
			),
		)
		validate_transition(
			BookRunStatus.APPROVED,
			BookRunStatus.SEALING,
			TransitionContext(
				actor="manager@example.com",
				roles=frozenset({"GT Books Manager"}),
				idempotency_key="run:1",
			),
		)

	def test_preparer_cannot_approve(self):
		with self.assertRaises(InvalidTransition):
			validate_transition(
				BookRunStatus.READY_FOR_REVIEW,
				BookRunStatus.APPROVED,
				TransitionContext(
					actor="same@example.com",
					prepared_by="same@example.com",
					reviewed_by="reviewer@example.com",
					roles=frozenset({"GT Books Manager"}),
					preflight_passed=True,
				),
			)

	def test_reviewer_cannot_be_final_approver(self):
		with self.assertRaises(InvalidTransition):
			validate_transition(
				BookRunStatus.READY_FOR_REVIEW,
				BookRunStatus.APPROVED,
				TransitionContext(
					actor="reviewer@example.com",
					prepared_by="preparer@example.com",
					reviewed_by="reviewer@example.com",
					roles=frozenset({"GT Books Manager"}),
					preflight_passed=True,
				),
			)

	def test_sealed_run_only_allows_supersession(self):
		with self.assertRaises(InvalidTransition):
			validate_transition(
				BookRunStatus.SEALED,
				BookRunStatus.QUEUED,
				TransitionContext(actor="manager@example.com"),
			)
		with self.assertRaises(InvalidTransition):
			validate_transition(
				BookRunStatus.SEALED,
				BookRunStatus.SUPERSEDED,
				TransitionContext(actor="user@example.com"),
			)
		validate_transition(
			BookRunStatus.SEALED,
			BookRunStatus.SUPERSEDED,
			TransitionContext(actor="manager@example.com", roles=frozenset({"GT Books Manager"})),
		)


if __name__ == "__main__":
	unittest.main()
