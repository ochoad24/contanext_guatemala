from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from contanext_guatemala.fel.post_commit import schedule_after_commit


class CallbackRegistry:
	def __init__(self):
		self.callbacks = []

	def add(self, callback):
		self.callbacks.append(callback)


class TestPostCommitSpike(TestCase):
	def setUp(self):
		self.registry = CallbackRegistry()
		self.local = SimpleNamespace()
		self.db = SimpleNamespace(after_commit=self.registry)

	def _schedule(self, immediate, enqueue):
		with (
			patch("contanext_guatemala.fel.post_commit.frappe.local", self.local),
			patch("contanext_guatemala.fel.post_commit.frappe.db", self.db),
			patch("contanext_guatemala.fel.post_commit.frappe.enqueue", enqueue),
			patch("contanext_guatemala.fel.post_commit.frappe.log_error"),
		):
			result = schedule_after_commit(
				key="Company A::Sales Invoice::SINV-1",
				immediate=immediate,
				fallback_job="contanext_guatemala.fel.jobs.process_operation",
				kwargs={"operation_name": "FEL-OP-1"},
			)
			return result

	def test_does_not_execute_before_commit_and_executes_after_commit(self):
		immediate = Mock()
		result = self._schedule(immediate, Mock())

		immediate.assert_not_called()
		self.assertEqual(result.mode, "AFTER_COMMIT")
		self.registry.callbacks[0]()
		immediate.assert_called_once_with(operation_name="FEL-OP-1")

	def test_rollback_discards_callback_without_side_effect(self):
		immediate = Mock()
		enqueue = Mock()
		self._schedule(immediate, enqueue)

		self.registry.callbacks.clear()  # equivalent to Frappe rollback callback disposal

		immediate.assert_not_called()
		enqueue.assert_not_called()

	def test_failure_after_commit_uses_short_queue_fallback(self):
		immediate = Mock(side_effect=RuntimeError("local attempt failed"))
		enqueue = Mock()
		self._schedule(immediate, enqueue)

		with (
			patch("contanext_guatemala.fel.post_commit.frappe.enqueue", enqueue),
			patch("contanext_guatemala.fel.post_commit.frappe.log_error"),
		):
			self.registry.callbacks[0]()

		enqueue.assert_called_once_with(
			"contanext_guatemala.fel.jobs.process_operation",
			queue="short",
			job_id="fel-post-commit::Company A::Sales Invoice::SINV-1",
			operation_name="FEL-OP-1",
		)

	def test_same_key_is_registered_once_per_request(self):
		immediate = Mock()
		first = self._schedule(immediate, Mock())
		second = self._schedule(immediate, Mock())

		self.assertEqual(first.mode, "AFTER_COMMIT")
		self.assertEqual(second.mode, "ALREADY_REGISTERED")
		self.assertEqual(len(self.registry.callbacks), 1)
