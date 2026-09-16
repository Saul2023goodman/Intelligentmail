"""Extension-peer protocol tests for schedule placement, Cancellation and Recall."""

import unittest
from datetime import timedelta, timezone

from smartmail import SmartMailError
from smartmail.mailbox import NetEase163ExtensionMailbox, MailboxCapabilityError
from tests.extension_fixture import FixtureExtension
from tests.test_execution import ExecutionTestCase, SUBJECT
from tests.test_schedules import BEIJING, SCHEDULE_SUBJECT


class ExtensionScheduleTests(ExecutionTestCase):
    def connect(self, **kwargs):
        extension = FixtureExtension(self.home, **kwargs)
        self.addCleanup(extension.close)
        self.core.mailbox = NetEase163ExtensionMailbox(
            self.home, enable_send=True, enable_schedule=True, enable_recall=True, timeout=5)
        return extension

    def scheduled_confirmation(self, subject=SCHEDULE_SUBJECT, minutes=120):
        preparation, _ = self.ready_preparation(attach=False, subject=subject)
        when = self.core._instant().astimezone(BEIJING) + timedelta(minutes=minutes)
        execution = {"kind": "scheduled", "scheduled_at": when.isoformat(),
                     "scheduled_utc": when.astimezone(timezone.utc).isoformat(),
                     "timezone": "Asia/Shanghai"}
        return preparation, self.core.confirm(preparation["id"], execution=execution)

    def test_schedule_command_crosses_the_bridge_and_preserves_the_external_identity(self):
        preparation, confirmation = self.scheduled_confirmation()
        extension = self.connect()

        result = self.core.place_schedule(confirmation["id"])

        schedule = result["schedule"]
        self.assertEqual(schedule["state"], "externally_scheduled")
        self.assertEqual(schedule["external_id"], "761:ext-schedule-1")
        self.assertEqual(extension.schedule_requests[0]["kind"], "scheduled")
        self.assertEqual(extension.schedule_requests[0]["binding"]["attempt_id"],
                         result["attempt"]["id"])
        self.assertGreater(extension.schedule_requests[0]["scheduled_epoch_ms"], 0)
        # No Sent Record: the mailbox owns execution while SmartMail is offline.
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])
        self.assertFalse(extension.errors)

    def test_schedule_capability_is_independent_of_immediate_send(self):
        preparation, confirmation = self.scheduled_confirmation()
        extension = FixtureExtension(self.home)
        self.addCleanup(extension.close)
        send_only = NetEase163ExtensionMailbox(self.home, enable_send=True, timeout=2)
        caps = send_only.capabilities()
        self.assertTrue(caps["immediate_send"]["available"])
        self.assertFalse(caps["native_scheduling"]["available"])
        self.core.mailbox = send_only
        with self.assertRaises(SmartMailError):
            self.core.place_schedule(confirmation["id"])
        self.assertEqual(extension.schedule_requests, [])

    def test_immediate_confirmation_cannot_grant_a_schedule_permit(self):
        preparation, _ = self.ready_preparation(subject=SCHEDULE_SUBJECT)
        immediate = self.core.confirm(preparation["id"])
        extension = self.connect()
        # Schedule placement is its own capability; an immediate Confirmation is never used.
        with self.assertRaises(SmartMailError):
            self.core.place_schedule(immediate["id"])
        self.assertEqual(extension.schedule_requests, [])

    def test_cancel_schedule_requires_its_own_cancellation_confirmation(self):
        preparation, confirmation = self.scheduled_confirmation()
        extension = self.connect()
        placed = self.core.place_schedule(confirmation["id"])["schedule"]
        schedule_cancel = self.core.confirm_schedule_cancellation(placed["id"])["confirmation"]
        result = self.core.run_schedule_cancellation(schedule_cancel["id"])
        self.assertEqual(result["schedule"]["state"], "cancelled")
        self.assertEqual(extension.cancel_requests[0]["external_id"], placed["external_id"])
        self.assertEqual(extension.cancel_requests[0]["kind"], "cancel_schedule")

    def test_uncertain_cancel_from_peer_pauses_without_a_cancelled_state(self):
        _, confirmation = self.scheduled_confirmation()
        extension = self.connect(cancel_outcome={
            "outcome": "unknown", "detail": "draft not observable after move"})
        placed = self.core.place_schedule(confirmation["id"])["schedule"]
        cancel = self.core.confirm_schedule_cancellation(placed["id"])["confirmation"]
        result = self.core.run_schedule_cancellation(cancel["id"])
        self.assertEqual(result["schedule"]["state"], "cancel_unknown")
        self.assertEqual(result["flow"]["state"], "paused")

    def test_recall_runs_through_peer_and_is_recorded_without_blocking(self):
        preparation, _ = self.ready_preparation(subject=SUBJECT)
        confirmation = self.core.confirm(preparation["id"])
        extension = self.connect(recall_outcome={
            "outcome": "recall_pending", "reference": "761:ext-sent-9",
            "external_id": "761:ext-sent-9", "mailbox_address": "student@163.com",
            "evidence": {"response_code": "S_OK", "recall_result": {"a": 0}}})
        attempt = self.core.run_execution([confirmation["id"]])["attempts"][0]
        record = self.core.get_sent_record(attempt["sent_record_id"])
        # Point the Sent Record at a recallable identity for this protocol test.
        with self.core._db:
            self.core._db.execute("UPDATE sent_records SET reference = ? WHERE id = ?",
                                  ("761:ext-sent-9", record["id"]))
        record = self.core.get_sent_record(record["id"])
        recall_confirmation = self.core.confirm_recall(record["id"])["confirmation"]
        outcome = self.core.run_recall(recall_confirmation["id"])
        self.assertEqual(outcome["recall_outcome"], "recall_pending")
        self.assertFalse(outcome["blocks_completion"])
        self.assertEqual(extension.recall_requests[0]["external_id"], "761:ext-sent-9")

    def test_disabled_recall_adapter_refuses_to_enqueue(self):
        extension = FixtureExtension(self.home)
        self.addCleanup(extension.close)
        adapter = NetEase163ExtensionMailbox(self.home, enable_schedule=True, timeout=2)
        self.core.mailbox = adapter
        self.assertFalse(adapter.capabilities()["recall"]["available"])
        with self.assertRaises(MailboxCapabilityError):
            adapter.recall_confirmed(
                {"kind": "recall", "sender": "student@163.com", "external_id": "x"},
                confirmation_id="c", attempt_id="a")


if __name__ == "__main__":
    unittest.main()
