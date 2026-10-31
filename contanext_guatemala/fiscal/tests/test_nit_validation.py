from unittest import TestCase

from contanext_guatemala.validation import (
	is_valid_nit_format,
	normalize_nit,
	validate_nit_format,
)


class TestNITValidation(TestCase):
	def test_normalize_nit_removes_whitespace_and_uppercases_verifier(self):
		self.assertEqual(normalize_nit("  1234 567 - k\t"), "1234567-K")
		self.assertEqual(normalize_nit(None), "")

	def test_validate_nit_format_accepts_supported_syntaxes(self):
		for value, expected in (
			("1234567-8", "1234567-8"),
			(" 1234567 - k ", "1234567-K"),
			("12345678", "12345678"),
		):
			with self.subTest(value=value):
				self.assertEqual(validate_nit_format(value), expected)

	def test_validate_nit_format_rejects_invalid_values(self):
		for value in (None, "", "CF", "ABC-1", "123-XY", "123--4", "123456789012-3"):
			with self.subTest(value=value):
				with self.assertRaisesRegex(ValueError, "Formato de NIT inválido"):
					validate_nit_format(value)

	def test_empty_value_is_only_accepted_when_explicitly_allowed(self):
		self.assertEqual(validate_nit_format(" \t", allow_empty=True), "")

	def test_validity_predicate_normalizes_without_raising(self):
		self.assertTrue(is_valid_nit_format(" 1234567 - k "))
		self.assertFalse(is_valid_nit_format(None))
		self.assertFalse(is_valid_nit_format("NIT-INVALIDO"))
