"""Ticket 12: native schedules, Cancellation, Scheduled Replacement, Recall, direct changes."""

import unittest
from datetime import datetime, timedelta, timezone

from smartmail import SmartMailError
from smartmail.mailbox import ControlledMailbox
from tests.test_execution import (
    ExecutionTestCase, SUBJECT, DEFAULT_ROWS, DECLARATION, DRAFT_NAME)

BEIJING = timezone(timedelta(hours=8))
SCHEDULE_SUBJECT = "Scheduled PhD supervision enquiry"


class SchedulesTestCase(ExecutionTestCase):
    def use_schedule_mailbox(self, *schedule_outcomes, cancel_outcomes=(), recall_outcomes=()):
        mailbox = ControlledMailbox(
            schedule_outcomes=list(schedule_outcomes),
            cancel_outcomes=list(cancel_outcomes),
            recall_outcomes=list(recall_outcomes),
            allow_schedule=True, allow_recall=True)
        self.core.mailbox = mailbox
        return mailbox

    def scheduled_confirmation(self, subject=SCHEDULE_SUBJECT, attach=False, *, minutes=120):
        preparation, _ = self.ready_preparation(attach=attach, subject=subject)
        when = self.core._instant().astimezone(BEIJING) + timedelta(minutes=minutes)
        execution = {"kind": "scheduled", "scheduled_at": when.isoformat(),
                     "scheduled_utc": when.astimezone(timezone.utc).isoformat(),
                     "timezone": "Asia/Shanghai"}
        return preparation, self.core.confirm(preparation["id"], execution=execution)

    def place(self, confirmation, mailbox=None):
        result = self.core.place_schedule(confirmation["id"])
        return result

    def two_ready(self):
        """Two Ready Preparations for two supervisors in one Campaign."""
        rows = [list(DEFAULT_ROWS[0]),
                ["Example University", "Dr Blair Blue", "blair@example.edu", ""]]
        (cv_name, cv_path), _ = self.cv()
        imported = self.import_bundle([
            (DRAFT_NAME, ["Email: alex@example.edu", "", "", "", "Dear Dr Green,", "", DECLARATION]),
            ("Example University_Dr Blair Blue.docx",
             ["Email: blair@example.edu", "", "", "", "Dear Dr Blue,", "", DECLARATION]),
        ], master_rows=rows, extra=[(cv_name, cv_path)])
        ids = self.core.prepare_from_documents(imported["id"])["preparation_ids"]
        for preparation_id in ids:
            self.core.set_subject(preparation_id, SCHEDULE_SUBJECT)
            slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
            self.core.confirm_attachment(preparation_id, slot["id"])
        return [self.core.get_preparation(preparation_id) for preparation_id in ids]

    def scheduled_for(self, preparation, minutes, subject):
        when = self.core._instant().astimezone(BEIJING) + timedelta(minutes=minutes)
        execution = {"kind": "scheduled", "scheduled_at": when.isoformat(),
                     "scheduled_utc": when.astimezone(timezone.utc).isoformat(),
                     "timezone": "Asia/Shanghai"}
        self.core.set_subject(preparation["id"], subject)
        return preparation, self.core.confirm(preparation["id"], execution=execution)


class PlacementTests(SchedulesTestCase):
    def test_confirmed_schedule_is_placed_and_tracked_without_a_sent_record(self):
        preparation, confirmation = self.scheduled_confirmation()
        mailbox = self.use_schedule_mailbox()

        result = self.place(confirmation)

        self.assertEqual(result["attempt"]["state"], "externally_scheduled")
        schedule = result["schedule"]
        self.assertEqual(schedule["state"], "externally_scheduled")
        self.assertEqual(schedule["external_id"], "761:controlled-schedule-1")
        self.assertEqual(schedule["mailbox_address"], "student@163.com")
        self.assertEqual(schedule["preparation_id"], preparation["id"])
        self.assertEqual(mailbox.schedule_requests[0]["kind"], "scheduled")
        self.assertEqual(mailbox.schedule_requests[0]["subject"], SCHEDULE_SUBJECT)
        self.assertGreater(mailbox.schedule_requests[0]["scheduled_epoch_ms"],
                           datetime.now(timezone.utc).timestamp() * 1000 - 1000)
        # Externally Scheduled is not Sent: no immutable Sent Record exists yet.
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])

    def test_scheduling_stays_disabled_without_the_independent_capability(self):
        _, confirmation = self.scheduled_confirmation()
        self.mailbox = ControlledMailbox()
        self.core.mailbox = self.mailbox
        self.assertFalse(
            self.core.mailbox_capabilities()["capabilities"]["native_scheduling"]["available"])
        with self.assertRaises(SmartMailError):
            self.place(confirmation)
        self.assertEqual(self.mailbox.schedule_requests, [])

    def test_immediate_send_is_not_substituted_for_a_schedule_even_with_send_enabled(self):
        _, confirmation = self.scheduled_confirmation()
        # No schedule capability, but immediate send would work: the kind must still be refused.
        self.mailbox = ControlledMailbox()
        self.core.mailbox = self.mailbox
        with self.assertRaises(SmartMailError):
            self.core.run_execution([confirmation["id"]])
        self.assertEqual(self.mailbox.requests, [])
        self.assertEqual(self.mailbox.schedule_requests, [])

    def test_elapsed_confirmed_time_is_refused(self):
        preparation, _ = self.ready_preparation(subject=SCHEDULE_SUBJECT)
        past = self.core._instant().astimezone(BEIJING) - timedelta(minutes=5)
        execution = {"kind": "scheduled", "scheduled_at": past.isoformat(),
                     "scheduled_utc": past.astimezone(timezone.utc).isoformat(),
                     "timezone": "Asia/Shanghai"}
        confirmation = self.core.confirm(preparation["id"], execution=execution)
        self.use_schedule_mailbox()
        with self.assertRaises(SmartMailError):
            self.place(confirmation)

    def test_unknown_placement_pauses_and_is_never_duplicated(self):
        _, confirmation = self.scheduled_confirmation()
        mailbox = self.use_schedule_mailbox("unknown")

        result = self.place(confirmation)
        self.assertEqual(result["attempt"]["state"], "unknown")
        self.assertIsNone(result["schedule"])
        self.assertEqual(result["flow"]["state"], "paused")
        self.assertEqual(result["flow"]["reason"], "unknown_outcome")
        self.assertEqual(len(mailbox.schedule_requests), 1)
        # A second attempt must not resubmit while the first is unresolved.
        with self.assertRaises(SmartMailError):
            self.place(confirmation)
        self.assertEqual(len(mailbox.schedule_requests), 1)
        # Elapsed time alone never turns it into Sent.
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])

    def test_failed_placement_does_not_create_a_schedule_or_sent_record(self):
        _, confirmation = self.scheduled_confirmation()
        self.use_schedule_mailbox("failed")
        result = self.place(confirmation)
        self.assertEqual(result["attempt"]["state"], "failed")
        self.assertIsNone(result["schedule"])
        self.assertEqual(self.core.list_external_schedules(), [])
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])

    def test_two_confirmed_schedules_for_the_same_preparation_are_rejected(self):
        _, confirmation = self.scheduled_confirmation()
        self.use_schedule_mailbox("scheduled", "scheduled")
        self.place(confirmation)
        with self.assertRaises(SmartMailError):
            self.place(confirmation)


class CancellationTests(SchedulesTestCase):
    def _placed(self):
        _, confirmation = self.scheduled_confirmation()
        self.use_schedule_mailbox()
        placed = self.place(confirmation)
        return placed["schedule"]

    def test_observed_removal_records_cancellation(self):
        schedule = self._placed()
        mailbox = self.core.mailbox
        review = self.core.review_schedule_cancellation(schedule["id"])
        self.assertTrue(review["requires_explicit_confirmation"])
        cancel_confirmation = self.core.confirm_schedule_cancellation(schedule["id"])["confirmation"]
        self.assertEqual(cancel_confirmation["execution"]["kind"], "cancellation")
        result = self.core.run_schedule_cancellation(cancel_confirmation["id"])
        self.assertEqual(result["attempt"]["state"], "cancelled")
        self.assertEqual(result["schedule"]["state"], "cancelled")
        self.assertEqual(mailbox.cancel_requests[0]["external_id"], schedule["external_id"])
        self.assertEqual(self.core.get_confirmation(cancel_confirmation["id"])["status"], "consumed")

    def test_uncertain_removal_pauses_without_asserting_cancellation(self):
        schedule = self._placed()
        self.core.mailbox = ControlledMailbox(
            cancel_outcomes=["unknown"], allow_schedule=True, allow_recall=True)
        cancel = self.core.confirm_schedule_cancellation(schedule["id"])["confirmation"]
        result = self.core.run_schedule_cancellation(cancel["id"])
        self.assertEqual(result["attempt"]["state"], "unknown")
        self.assertEqual(result["schedule"]["state"], "cancel_unknown")
        self.assertEqual(result["flow"]["state"], "paused")
        self.assertEqual(result["flow"]["reason"], "unknown_outcome")

    def test_cancellation_when_message_already_sent_freezes_sent_record_and_pauses(self):
        schedule = self._placed()
        self.core.mailbox = ControlledMailbox(
            cancel_outcomes=["already_sent"], allow_schedule=True, allow_recall=True)
        cancel = self.core.confirm_schedule_cancellation(schedule["id"])["confirmation"]
        result = self.core.run_schedule_cancellation(cancel["id"])
        self.assertEqual(result["schedule"]["state"], "sent")
        self.assertEqual(result["flow"]["reason"], "schedule_sent_during_cancel")
        sent = self.core.list_sent_records(self.campaign["id"])
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0]["reference"], schedule["external_id"])
        self.assertTrue(sent[0]["evidence"]["frozen_from_schedule"])

    def test_cancellation_requires_an_externally_scheduled_state(self):
        schedule = self._placed()
        cancel = self.core.confirm_schedule_cancellation(schedule["id"])["confirmation"]
        self.core.run_schedule_cancellation(cancel["id"])
        # Once observed removed, a second Cancellation Confirmation cannot be created.
        with self.assertRaises(SmartMailError):
            self.core.confirm_schedule_cancellation(schedule["id"])

    def test_authentication_interruption_keeps_the_schedule_owned_by_the_mailbox(self):
        schedule = self._placed()
        self.core.mailbox = ControlledMailbox(
            cancel_outcomes=["authentication_required"], allow_schedule=True, allow_recall=True)
        cancel = self.core.confirm_schedule_cancellation(schedule["id"])["confirmation"]
        result = self.core.run_schedule_cancellation(cancel["id"])
        self.assertEqual(result["schedule"]["state"], "externally_scheduled")
        self.assertEqual(result["flow"]["reason"], "authentication_required")
        self.assertEqual(result["attempt"]["state"], "unknown")

    def test_pausing_smartmail_leaves_other_external_schedules_active(self):
        preparations = self.two_ready()
        mailbox = self.use_schedule_mailbox("scheduled", "scheduled")
        _, first_confirmation = self.scheduled_for(preparations[0], 120, SCHEDULE_SUBJECT)
        first = self.place(first_confirmation)["schedule"]
        _, second_confirmation = self.scheduled_for(
            preparations[1], 300, "Second scheduled enquiry")
        second_placed = self.place(second_confirmation)["schedule"]
        # Cancelling only the first schedule never touches the second.
        self.core.mailbox = ControlledMailbox(
            cancel_outcomes=["removed"], allow_schedule=True, allow_recall=True)
        cancel = self.core.confirm_schedule_cancellation(first["id"])["confirmation"]
        self.core.run_schedule_cancellation(cancel["id"])
        second = self.core.get_external_schedule(second_placed["id"])
        self.assertEqual(second["state"], "externally_scheduled")
        self.assertEqual(self.core.mailbox.cancel_requests[0]["external_id"], first["external_id"])


class ReplacementTests(SchedulesTestCase):
    def _original(self):
        preparations = self.two_ready()
        _, original_confirmation = self.scheduled_for(preparations[0], 120, SCHEDULE_SUBJECT)
        self.use_schedule_mailbox()
        return self.place(original_confirmation)["schedule"], preparations[1]

    def _replacement(self, second_preparation, subject="Replacement scheduled enquiry"):
        return self.scheduled_for(second_preparation, 240, subject)

    def test_replacement_confirms_exact_removal_plus_new_schedule_without_transfer(self):
        original, second_preparation = self._original()
        _, replacement = self._replacement(second_preparation)
        bound = self.core.confirm_schedule_replacement(original["id"], replacement["id"])
        self.assertEqual(bound["confirmation"]["execution"]["kind"], "replacement")
        self.assertEqual(bound["confirmation"]["execution"]["external_id"],
                         original["external_id"])

    def test_replacement_verifies_removal_before_submitting_the_new_schedule(self):
        original, second_preparation = self._original()
        _, replacement = self._replacement(second_preparation)
        bound = self.core.confirm_schedule_replacement(original["id"], replacement["id"])
        mailbox = ControlledMailbox(
            schedule_outcomes=["scheduled"], cancel_outcomes=["unknown"],
            allow_schedule=True, allow_recall=True)
        self.core.mailbox = mailbox
        result = self.core.run_schedule_replacement(bound["confirmation"]["id"])
        self.assertFalse(result["replacement_placed"])
        self.assertEqual(result["phase"], "removal_unverified")
        self.assertEqual(mailbox.schedule_requests, [], "replacement must not be submitted")
        self.assertEqual(len(mailbox.cancel_requests), 1)

    def test_successful_replacement_marks_old_replaced_and_new_scheduled(self):
        original, second_preparation = self._original()
        replacement_prep, replacement = self._replacement(second_preparation)
        bound = self.core.confirm_schedule_replacement(original["id"], replacement["id"])
        self.core.mailbox = ControlledMailbox(
            schedule_outcomes=["scheduled"], cancel_outcomes=["removed"],
            allow_schedule=True, allow_recall=True)
        result = self.core.run_schedule_replacement(bound["confirmation"]["id"])
        self.assertTrue(result["replacement_placed"])
        self.assertEqual(result["phase"], "complete")
        schedules = {s["preparation_id"]: s for s in self.core.list_external_schedules()}
        self.assertEqual(schedules[original["preparation_id"]]["state"], "replaced")
        new = schedules[replacement_prep["id"]]
        self.assertEqual(new["state"], "externally_scheduled")
        self.assertEqual(new["replaces_schedule_id"], original["id"])

    def test_failed_replacement_submission_never_restores_the_removed_original(self):
        original, second_preparation = self._original()
        _, replacement = self._replacement(second_preparation)
        bound = self.core.confirm_schedule_replacement(original["id"], replacement["id"])
        self.core.mailbox = ControlledMailbox(
            schedule_outcomes=["unknown"], cancel_outcomes=["removed"],
            allow_schedule=True, allow_recall=True)
        result = self.core.run_schedule_replacement(bound["confirmation"]["id"])
        self.assertFalse(result["replacement_placed"])
        self.assertEqual(result["phase"], "replacement_submission_unknown")
        # The original was observed removed and stays removed; SmartMail does not restore it.
        self.assertEqual(self.core.get_external_schedule(original["id"])["state"], "cancelled")
        self.assertEqual(result["flow"]["reason"], "unknown_outcome")

    def test_original_sent_during_replacement_freezes_and_blocks_new_communication(self):
        original, second_preparation = self._original()
        _, replacement = self._replacement(second_preparation)
        bound = self.core.confirm_schedule_replacement(original["id"], replacement["id"])
        self.core.mailbox = ControlledMailbox(
            cancel_outcomes=["already_sent"], allow_schedule=True, allow_recall=True)
        result = self.core.run_schedule_replacement(bound["confirmation"]["id"])
        self.assertFalse(result["replacement_placed"])
        self.assertEqual(result["phase"], "original_sent")
        self.assertEqual(self.core.get_external_schedule(original["id"])["state"], "sent")
        self.assertEqual(self.core.mailbox.schedule_requests, [])
        self.assertEqual(len(self.core.list_sent_records(self.campaign["id"])), 1)


class DirectChangeReconciliationTests(SchedulesTestCase):
    def _placed(self, scheduled_beijing="2026-09-18 12:00:00"):
        _, confirmation = self.scheduled_confirmation()
        mailbox = self.use_schedule_mailbox()
        placed = self.place(confirmation)
        # Controlled evidence normally lacks the Beijing stamp; set it for comparison.
        schedule = placed["schedule"]
        return confirmation, schedule, mailbox

    def _observation(self, messages, mailbox="student@163.com"):
        return {"status": "complete", "mailbox_address": mailbox,
                "observed_at": "2026-09-17T08:00:00+00:00",
                "coverage": {"complete": False, "folders": []},
                "messages": messages}

    def test_still_active_schedule_is_observed_without_local_mutation(self):
        _, schedule, mailbox = self._placed()
        expected = self.core._platform_evidence(schedule)["scheduled_beijing"]
        message = {"direction": "outbound", "folder": "drafts",
                   "platform_reference": schedule["external_id"],
                   "counterpart": "alex@example.edu", "subject": SCHEDULE_SUBJECT,
                   "observed_time": expected, "status": "scheduled",
                   "ambiguity": "", "evidence": {"scheduleDelivery": True}}
        mailbox._observations.append(self._observation([message]))
        result = self.core.reconcile_external_schedules(self.student["id"])
        findings = {f["finding"] for f in result["reconciliation"]["findings"]}
        self.assertIn("external_schedule_still_active", findings)
        self.assertEqual(self.core.get_external_schedule(schedule["id"])["state"],
                         "externally_scheduled")

    def test_direct_external_time_edit_is_a_discrepancy_that_pauses_without_restoring(self):
        _, schedule, mailbox = self._placed()
        message = {"direction": "outbound", "folder": "drafts",
                   "platform_reference": schedule["external_id"],
                   "counterpart": "alex@example.edu", "subject": SCHEDULE_SUBJECT,
                   "observed_time": "2026-09-19 09:30:00", "status": "scheduled",
                   "ambiguity": "", "evidence": {"scheduleDelivery": True, "direct_edit": True}}
        mailbox._observations.append(self._observation([message]))
        result = self.core.reconcile_external_schedules(self.student["id"])
        findings = {f["finding"] for f in result["reconciliation"]["findings"]}
        self.assertIn("external_schedule_changed", findings)
        self.assertEqual(self.core.execution_status(self.campaign["id"])["reason"],
                         "external_schedule_changed")
        # External edits never inherit Confirmation: the local confirmation stays as it was.
        self.assertEqual(self.core.get_confirmation(schedule["confirmation_id"])["status"],
                         "active")

    def test_schedule_disappearing_does_not_become_sent_by_elapsed_time(self):
        _, schedule, mailbox = self._placed()
        mailbox._observations.append(self._observation([]))
        self.core.reconcile_external_schedules(self.student["id"])
        self.assertEqual(self.core.get_external_schedule(schedule["id"])["state"],
                         "externally_scheduled")
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])

    def test_observed_sent_evidence_freezes_the_sent_record(self):
        _, schedule, mailbox = self._placed()
        message = {"direction": "outbound", "folder": "sent",
                   "platform_reference": schedule["external_id"],
                   "counterpart": "alex@example.edu", "subject": SCHEDULE_SUBJECT,
                   "observed_time": "2026-09-18 12:00:05", "status": "sent",
                   "ambiguity": "", "evidence": {"sndStatus": 3}}
        mailbox._observations.append(self._observation([message]))
        result = self.core.reconcile_external_schedules(self.student["id"])
        self.assertTrue(any(f["state"] == "sent" for f in result["schedule_findings"]))
        self.assertEqual(self.core.get_external_schedule(schedule["id"])["state"], "sent")
        records = self.core.list_sent_records(self.campaign["id"])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["reference"], schedule["external_id"])

    def test_externally_owned_scheduled_draft_is_reported_as_non_local_evidence(self):
        _, _, mailbox = self._placed()
        message = {"direction": "outbound", "folder": "drafts",
                   "platform_reference": "foreign-schedule-1",
                   "counterpart": "someone-else@example.edu", "subject": "Not ours",
                   "observed_time": "2026-09-19 08:00:00", "status": "scheduled",
                   "ambiguity": "", "evidence": {"scheduleDelivery": True}}
        mailbox._observations.append(self._observation([message]))
        result = self.core.reconcile_external_schedules(self.student["id"])
        findings = {f["finding"] for f in result["reconciliation"]["findings"]}
        self.assertIn("observed_external_schedule", findings)


class RecallTests(SchedulesTestCase):
    def _sent_record(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        self.mailbox = ControlledMailbox()
        self.core.mailbox = self.mailbox
        attempt = self.core.run_execution([confirmation["id"]])["attempts"][0]
        return self.core.get_sent_record(attempt["sent_record_id"])

    def test_recall_capability_is_disabled_by_default(self):
        self.assertFalse(
            self.core.mailbox_capabilities()["capabilities"]["recall"]["available"])

    def test_recall_requires_its_own_explicit_confirmation_and_never_blocks(self):
        record = self._sent_record()
        mailbox = ControlledMailbox(recall_outcomes=["recalled"],
                                   allow_schedule=True, allow_recall=True)
        self.core.mailbox = mailbox
        confirmed = self.core.confirm_recall(record["id"])["confirmation"]
        self.assertEqual(confirmed["execution"]["kind"], "recall")
        result = self.core.run_recall(confirmed["id"])
        self.assertEqual(result["recall_outcome"], "recalled")
        self.assertFalse(result["blocks_completion"])
        self.assertEqual(mailbox.recall_requests[0]["external_id"], record["reference"])
        # The original Sent Record is untouched.
        self.assertEqual(self.core.get_sent_record(record["id"])["id"], record["id"])
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "idle")

    def test_unsupported_recall_is_reported_without_pausing_completion(self):
        record = self._sent_record()
        self.core.mailbox = ControlledMailbox(recall_outcomes=["unsupported"],
                                             allow_schedule=True, allow_recall=True)
        confirmed = self.core.confirm_recall(record["id"])["confirmation"]
        result = self.core.run_recall(confirmed["id"])
        self.assertEqual(result["recall_outcome"], "unsupported")
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "idle")


class ObservationSettingsTests(SchedulesTestCase):
    def test_periodic_observation_is_configurable_and_observation_only(self):
        configured = self.core.configure_observation(self.student["id"], 300)
        self.assertEqual(configured["observation_interval_seconds"], 300)
        self.assertIn("observation_only", configured["authority"])
        shown = self.core.get_observation_settings(self.student["id"])
        self.assertEqual(shown["observation_interval_seconds"], 300)
        self.core.configure_observation(self.student["id"], 0)
        self.assertEqual(
            self.core.get_observation_settings(self.student["id"])["observation_interval_seconds"], 0)

    def test_interval_must_be_a_non_negative_integer(self):
        with self.assertRaises(SmartMailError):
            self.core.configure_observation(self.student["id"], -5)


if __name__ == "__main__":
    unittest.main()
