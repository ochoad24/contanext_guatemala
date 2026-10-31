from unittest import TestCase

from contanext_guatemala.install import FEL_ROLES


class TestFELRoles(TestCase):
	def test_operational_and_billing_roles_are_explicit(self):
		self.assertEqual(
			set(FEL_ROLES),
			{
				"GT FEL User",
				"GT FEL Operator",
				"GT FEL Manager",
				"GT FEL Auditor",
				"GT FEL Billing Manager",
				"GT FEL Billing Auditor",
			},
		)
