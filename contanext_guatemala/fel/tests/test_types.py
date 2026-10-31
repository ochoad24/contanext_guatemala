from datetime import UTC, datetime
from unittest import TestCase

from contanext_guatemala.fel.types import (
	CertificationResult,
	DTEType,
	FELErrorClassification,
	FELOperationType,
	FELStatus,
)


class TestFELTypes(TestCase):
	def test_all_planned_dte_and_operation_types_are_explicit(self):
		self.assertEqual(
			set(DTEType),
			{DTEType.FACT, DTEType.FCAM, DTEType.NCRE, DTEType.NDEB, DTEType.FPEQ, DTEType.FCAP, DTEType.FESP},
		)
		self.assertEqual(
			set(FELOperationType),
			{
				FELOperationType.CERTIFY,
				FELOperationType.CANCEL,
				FELOperationType.RECONCILE,
				FELOperationType.QUERY_CONTRIBUTOR,
			},
		)

	def test_result_carries_certification_evidence_and_error_classification(self):
		certified_at = datetime(2026, 10, 30, tzinfo=UTC)
		result = CertificationResult(
			status=FELStatus.CERTIFIED,
			error_classification=FELErrorClassification.NONE,
			uuid="uuid",
			series="A",
			number="1",
			certified_at=certified_at,
			pdf=b"%PDF-1.7",
			warnings=("warning",),
			normalized_result={"error": 0},
		)

		self.assertEqual(result.certified_at, certified_at)
		self.assertEqual(result.pdf, b"%PDF-1.7")
		self.assertEqual(result.normalized_result["error"], 0)

	def test_state_model_distinguishes_retry_reconciliation_and_rejection(self):
		self.assertTrue(
			{FELStatus.RETRY_PENDING, FELStatus.RECONCILIATION_REQUIRED, FELStatus.REJECTED}.issubset(
				set(FELStatus)
			)
		)
