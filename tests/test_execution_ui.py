"""Batch workspace acceptance against persisted Core and controlled mailboxes."""
from datetime import timedelta

from smartmail.errors import SmartMailError
from smartmail.mailbox import ControlledMailbox, DisabledMailbox
from smartmail.ui import dispatch
from tests.test_execution import ExecutionTestCase


class ExecutionUiTests(ExecutionTestCase):
    def call(self, command, **args):
        return dispatch(self.core, {"command": f"execution_{command}", **args})

    def confirm(self, **request):
        review = self.call("review", **request)
        return self.call("confirm", **request, token=review["token"])

    def test_workspace_is_scoped_and_read_only(self):
        preparation, _ = self.ready_preparation()
        result = self.call("workspace", campaign_id=self.campaign["id"])
        self.assertEqual(result["reviews"][0]["preparation_id"], preparation["id"])
        self.assertTrue(result["reviews"][0]["ready"])
        self.assertEqual(result["plans"], [])
        self.assertEqual(result["confirmations"], [])
        other = self.core.create_campaign("Empty campaign")
        self.assertEqual(self.call("workspace", campaign_id=other["id"])["reviews"], [])
        self.assertEqual(self.mailbox.requests, [])

    def test_immediate_review_confirmation_and_execution_are_separate(self):
        preparation, _ = self.ready_preparation()
        confirmations = self.confirm(kind="immediate", preparation_ids=[preparation["id"]])
        self.assertEqual(self.mailbox.requests, [])
        result = self.call("run", confirmation_id=confirmations[0]["id"])
        self.assertEqual(result["attempts"][0]["state"], "sent")
        with self.assertRaises(SmartMailError):
            self.call("run", confirmation_id=confirmations[0]["id"])
        self.assertEqual(len(self.mailbox.requests), 1)

    def test_changed_review_requires_fresh_explicit_confirmation(self):
        preparation, _ = self.ready_preparation()
        request = {"kind": "immediate", "preparation_ids": [preparation["id"]]}
        reviewed = self.call("review", **request)
        self.core.set_subject(preparation["id"], "Changed after review")
        with self.assertRaisesRegex(SmartMailError, "Review again"):
            self.call("confirm", **request, token=reviewed["token"])
        self.assertEqual(self.core.list_confirmations(self.campaign["id"]), [])

    def test_rules_plan_adjustment_and_confirmation_use_core(self):
        preparation, _ = self.ready_preparation()
        self.call("configure", campaign_id=self.campaign["id"], timezone="Asia/Shanghai",
                  windows=["MON-SUN 00:00-23:59"], spacing_minutes=30, daily_limit=4, horizon_days=7)
        plan = self.call("propose", campaign_id=self.campaign["id"])
        self.assertEqual(plan["configuration"]["daily_limit"], 4)
        reviewed = self.call("review", kind="plan", plan_id=plan["id"])
        next_time = self.core._instant() + timedelta(days=1)
        adjusted = self.call("adjust", plan_id=plan["id"], preparation_id=preparation["id"],
                             scheduled_at=next_time.isoformat())
        self.assertNotEqual(plan["proposals"][0]["scheduled_at"], adjusted["proposals"][0]["scheduled_at"])
        with self.assertRaisesRegex(SmartMailError, "Review again"):
            self.call("confirm", kind="plan", plan_id=plan["id"], token=reviewed["token"])
        confirmed = self.confirm(kind="plan", plan_id=plan["id"])
        self.assertEqual(confirmed["status"], "confirmed")
        self.assertEqual(self.mailbox.requests, [])
        self.call("adjust", plan_id=plan["id"], preparation_id=preparation["id"],
                  scheduled_at=(next_time + timedelta(hours=1)).isoformat())
        confirmation_id = confirmed["proposals"][0]["confirmation_id"]
        self.assertEqual(self.core.get_confirmation(confirmation_id)["status"], "invalidated")

    def test_schedule_and_cancellation_are_observed_not_assumed(self):
        self.ready_preparation()
        self.core.mailbox = ControlledMailbox(allow_schedule=True)
        plan = self.call("propose", campaign_id=self.campaign["id"])
        confirmed = self.confirm(kind="plan", plan_id=plan["id"])
        placed = self.call("run", confirmation_id=confirmed["proposals"][0]["confirmation_id"])
        self.assertEqual(placed["schedule"]["state"], "externally_scheduled")
        cancellation = self.confirm(kind="cancellation", schedule_id=placed["schedule"]["id"])
        self.assertEqual(self.core.get_external_schedule(placed["schedule"]["id"])["state"], "externally_scheduled")
        self.call("run", confirmation_id=cancellation["confirmation"]["id"])
        self.assertEqual(self.core.get_external_schedule(placed["schedule"]["id"])["state"], "cancelled")
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])

    def test_disabled_capability_never_creates_attempt(self):
        preparation, _ = self.ready_preparation()
        confirmed = self.confirm(kind="immediate", preparation_ids=[preparation["id"]])
        self.core.mailbox = DisabledMailbox()
        with self.assertRaisesRegex(SmartMailError, "disabled"):
            self.call("run", confirmation_id=confirmed[0]["id"])
        self.assertEqual(self.core.list_execution_attempts(self.campaign["id"]), [])

    def test_unknown_outcome_pauses_and_is_not_retried(self):
        preparation, _ = self.ready_preparation()
        self.script("unknown")
        confirmed = self.confirm(kind="immediate", preparation_ids=[preparation["id"]])
        result = self.call("run", confirmation_id=confirmed[0]["id"])
        self.assertTrue(result["paused"])
        with self.assertRaises(SmartMailError):
            self.call("run", confirmation_id=confirmed[0]["id"])
        self.assertEqual(len(self.mailbox.requests), 1)

    def test_replacement_requires_fresh_confirmation_and_verified_removal(self):
        preparation, _ = self.ready_preparation()
        self.core.mailbox = ControlledMailbox(allow_schedule=True)
        original = self.core.confirm(preparation["id"], {"kind": "scheduled",
                                     "scheduled_at": (self.core._instant() + timedelta(days=1)).isoformat()})
        placed = self.call("run", confirmation_id=original["id"])["schedule"]
        fresh = self.core.rewrite(preparation["id"], preparation["source"]["id"])
        self.core.set_subject(fresh["id"], "Replacement content")
        fresh = self.core.get_preparation(fresh["id"])
        for slot in fresh["attachment_slots"]:
            self.core.confirm_attachment(fresh["id"], slot["id"])
        replacement = self.core.confirm(fresh["id"], {"kind": "scheduled",
                                        "scheduled_at": (self.core._instant() + timedelta(days=2)).isoformat()})
        confirmed = self.confirm(kind="replacement", schedule_id=placed["id"],
                                 replacement_confirmation_id=replacement["id"])
        self.assertEqual(self.core.get_external_schedule(placed["id"])["state"], "externally_scheduled")
        result = self.call("run", confirmation_id=confirmed["confirmation"]["id"])
        self.assertTrue(result["replacement_placed"])
        self.assertEqual(self.core.get_external_schedule(placed["id"])["state"], "replaced")
