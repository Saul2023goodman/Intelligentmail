"""Ticket 08: crash recovery, operator takeover and reconcile-and-continue."""

import unittest

from smartmail import SmartMail, SmartMailError
from smartmail.mailbox import ControlledMailbox, MailboxCrash
from tests.test_execution import ExecutionTestCase, SUBJECT


class CrashBeforeSubmissionMailbox(ControlledMailbox):
    """The process fails at the adapter boundary before external submission."""

    def submit(self, request, attachments=None):
        raise RuntimeError("simulated process crash before submission")


class CrashDuringSubmissionMailbox(ControlledMailbox):
    """The adapter received the request but the process lost the response."""

    def submit(self, request, attachments=None):
        self.requests.append(request)
        raise RuntimeError("simulated process crash during submission")


class RestartRecoveryTests(ExecutionTestCase):
    def test_crash_before_submission_pauses_recovery_without_a_blind_retry(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        self.core.mailbox = CrashBeforeSubmissionMailbox()

        with self.assertRaises(RuntimeError):
            self.core.run_execution([confirmation["id"]])

        self.core.__exit__(None, None, None)
        retrying_mailbox = ControlledMailbox(outcomes=["sent"])
        with SmartMail(self.home, mailbox=retrying_mailbox) as restarted:
            status = restarted.execution_status(self.campaign["id"])
            self.assertEqual(status["state"], "paused")
            self.assertIn(status["reason"], {"recovery_required", "unknown_outcome"})
            with self.assertRaises(SmartMailError):
                restarted.run_execution([confirmation["id"]])
            self.assertEqual(retrying_mailbox.requests, [])
            self.assertEqual(
                restarted.get_execution_attempt(
                    restarted.list_execution_attempts(self.campaign["id"])[0]["id"]
                )["state"],
                "unknown",
            )

    def test_reconcile_and_continue_requires_positive_mailbox_evidence_before_sent(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        crashed = CrashDuringSubmissionMailbox()
        self.core.mailbox = crashed

        with self.assertRaises(RuntimeError):
            self.core.run_execution([confirmation["id"]])
        self.assertEqual(len(crashed.requests), 1)
        attempt_id = self.core.list_execution_attempts(self.campaign["id"])[0]["id"]

        self.core.__exit__(None, None, None)
        observation = {
            "status": "complete",
            "mailbox_address": "student@163.com",
            "coverage": {"complete": True, "supported_scope_complete": True},
            "messages": [{
                "direction": "outbound", "folder": "sent",
                "platform_reference": "manual-sent-1",
                "counterpart": "alex@example.edu", "subject": SUBJECT,
                "observed_time": "2026-09-11T10:00:00+00:00", "status": "sent",
                "evidence": {"marker": "mailbox-confirmed-sent"},
            }],
        }
        reconciling_mailbox = ControlledMailbox(observations=[observation])
        with SmartMail(self.home, mailbox=reconciling_mailbox) as restarted:
            result = restarted.reconcile_and_continue(attempt_id)

            self.assertTrue(result["resolved"])
            self.assertEqual(result["attempt"]["state"], "sent")
            self.assertIsNotNone(result["attempt"]["sent_record_id"])
            self.assertEqual(restarted.execution_status(self.campaign["id"])["state"], "idle")
            self.assertEqual(reconciling_mailbox.requests, [])

    def test_manual_takeover_reconciles_then_continues_the_next_confirmation(self):
        preparation_ids = self.two_ready_preparations()
        confirmations = self.core.confirm_preparations(preparation_ids)
        self.script({"outcome": "unknown", "detail": "operator takeover required"})

        first = self.core.run_execution([confirmations[0]["id"]])["attempts"][0]
        taken_over = self.core.take_over_execution(first["id"], detail="operator sent manually")
        self.assertEqual(taken_over["state"], "unknown")
        self.assertTrue(taken_over["evidence"]["manual_takeover"])

        observation = {
            "status": "complete",
            "mailbox_address": "student@163.com",
            "coverage": {"complete": True, "supported_scope_complete": True},
            "messages": [{
                "direction": "outbound", "folder": "sent",
                "platform_reference": "manual-takeover-sent",
                "counterpart": "alex@example.edu", "subject": SUBJECT,
                "observed_time": "2026-09-11T10:00:00+00:00", "status": "sent",
                "evidence": {"marker": "mailbox-confirmed-sent"},
            }],
        }
        continuing_mailbox = ControlledMailbox(
            outcomes=["sent"], observations=[observation])
        self.core.mailbox = continuing_mailbox

        result = self.core.reconcile_and_continue(
            first["id"], [confirmations[1]["id"]])

        self.assertTrue(result["resolved"])
        self.assertEqual(result["continued"]["attempts"][0]["state"], "sent")
        self.assertEqual(len(continuing_mailbox.requests), 1)
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "idle")


class ConfirmationValidityTests(ExecutionTestCase):
    def test_expired_confirmation_requires_a_newly_confirmed_time(self):
        preparation, _ = self.ready_preparation()
        expired = self.core.confirm(
            preparation["id"],
            execution={"kind": "immediate", "expires_at": "2020-01-01T00:00:00+00:00"},
        )

        with self.assertRaises(SmartMailError):
            self.core.run_execution([expired["id"]])
        self.assertEqual(self.mailbox.requests, [])
        self.assertEqual(
            self.core.execution_status(self.campaign["id"])["reason"],
            "confirmation_expired",
        )

        renewed = self.core.confirm(
            preparation["id"],
            execution={"kind": "immediate", "expires_at": "2099-01-01T00:00:00+00:00"},
        )
        self.assertNotEqual(renewed["id"], expired["id"])
        result = self.core.run_execution([renewed["id"]])
        self.assertEqual(result["attempts"][0]["state"], "sent")

    def test_resume_does_not_bypass_an_existing_execution_blocker(self):
        preparation_ids = self.two_ready_preparations()
        confirmations = self.core.confirm_preparations(preparation_ids)
        self.script("failed", "sent")

        first = self.core.run_execution([confirmations[0]["id"]])
        self.assertTrue(first["paused"])
        resumed = self.core.resume_execution(self.campaign["id"])

        self.assertEqual(resumed["attempts"], [])
        self.assertTrue(resumed["paused"])
        self.assertEqual(resumed["flow"]["reason"], "execution_failed")
        self.assertEqual(len(self.mailbox.requests), 1)


class CrashBoundaryTests(ExecutionTestCase):
    def test_crash_before_submission_keeps_intent_safe_to_resume(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        crashing = ControlledMailbox(
            outcomes=[{"crash": "before_submission"}])
        self.core.mailbox = crashing

        with self.assertRaises(MailboxCrash):
            self.core.run_execution([confirmation["id"]])
        attempt = self.core.list_execution_attempts(self.campaign["id"])[0]
        self.assertEqual(attempt["state"], "not_attempted")
        self.assertEqual(attempt["phase"], "intent_recorded")
        self.assertEqual(crashing.requests, [])

        resumed_mailbox = ControlledMailbox(outcomes=["sent"])
        self.core.mailbox = resumed_mailbox
        resumed = self.core.run_execution([confirmation["id"]])
        self.assertEqual(resumed["attempts"][0]["id"], attempt["id"])
        self.assertEqual(resumed["attempts"][0]["state"], "sent")
        self.assertEqual(len(resumed_mailbox.requests), 1)

    def test_authentication_interruption_pauses_execution_but_keeps_preparation_usable(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        self.script({"outcome": "authentication_required", "detail": "complete CAPTCHA"})

        result = self.core.run_execution([confirmation["id"]])

        self.assertTrue(result["paused"])
        self.assertEqual(result["flow"]["reason"], "authentication_required")
        self.assertEqual(result["attempts"][0]["state"], "unknown")
        self.assertEqual(result["attempts"][0]["evidence"]["interruption"],
                         "authentication_required")
        self.assertEqual(self.core.get_preparation(preparation["id"])["id"], preparation["id"])

    def test_crash_after_external_success_is_reconciled_without_a_second_request(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        crashed = ControlledMailbox(outcomes=[{"crash": "after_success"}])
        self.core.mailbox = crashed

        with self.assertRaises(MailboxCrash):
            self.core.run_execution([confirmation["id"]])
        attempt_id = self.core.list_execution_attempts(self.campaign["id"])[0]["id"]
        self.assertEqual(len(crashed.requests), 1)

        observation = {
            "status": "complete",
            "mailbox_address": "student@163.com",
            "coverage": {"complete": True, "supported_scope_complete": True},
            "messages": [{
                "direction": "outbound", "folder": "sent",
                "platform_reference": "controlled-after-success",
                "counterpart": "alex@example.edu", "subject": SUBJECT,
                "observed_time": "2026-09-11T10:00:00+00:00", "status": "sent",
                "evidence": {"marker": "mailbox-confirmed-sent"},
            }],
        }
        self.core.mailbox = ControlledMailbox(observations=[observation])
        result = self.core.reconcile_and_continue(attempt_id)

        self.assertTrue(result["resolved"])
        self.assertEqual(result["attempt"]["state"], "sent")
        self.assertEqual(self.core.mailbox.requests, [])

    def test_manual_acknowledgment_without_sent_evidence_stays_unknown(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        self.script({"outcome": "unknown", "detail": "operator intervention"})
        attempt = self.core.run_execution([confirmation["id"]])["attempts"][0]

        self.core.mailbox = ControlledMailbox(observations=[{
            "status": "partial",
            "mailbox_address": "student@163.com",
            "coverage": {"complete": False},
            "messages": [],
        }])
        result = self.core.reconcile_and_continue(attempt["id"], acknowledge=True)

        self.assertFalse(result["resolved"])
        self.assertEqual(result["attempt"]["state"], "unknown")
        self.assertIsNone(result["attempt"]["sent_record_id"])
        self.assertTrue(result["attempt"]["evidence"]["operator_acknowledged"])
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "paused")


if __name__ == "__main__":
    unittest.main()
