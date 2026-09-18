"""Ticket 13: one authorization, one Execution Run, traceable batch results."""
import json
from datetime import timedelta

from smartmail import SmartMail, SmartMailError
from smartmail.mailbox import ControlledMailbox, DisabledMailbox
from smartmail.execution_ui import dispatch_execution, run_kind_capability
from tests.test_execution import (
    DECLARATION,
    SUBJECT,
    ExecutionTestCase,
    bundle,
    document,
    draft_paragraphs,
    master,
)

SUPERVISORS = [
    ("Dr Alex Green", "alex@example.edu"),
    ("Dr Blair Blue", "blair@example.edu"),
    ("Dr Casey Grey", "casey@example.edu"),
    ("Dr Dana Dawn", "dana@example.edu"),
]


class RunTestCase(ExecutionTestCase):
    def import_bundle(self, documents, master_rows, extra=(), *, campaign=None, student=None):
        """Same bundle fixture, optionally scoped to another Campaign and Student."""
        master_path = master(self.directory / "master.xlsx", master_rows)
        members = [("master.xlsx", master_path)]
        for index, (name, paragraphs) in enumerate(documents):
            members.append((name, document(self.directory / f"draft-{index}.docx", paragraphs)))
        for name, item in extra:
            members.append((name, item))
        source = bundle(self.directory / "bundle.zip", members)
        return self.core.import_master(campaign or self.campaign["id"],
                                       student or self.student["id"], source)

    def ready_preparations(self, count=3, subject=SUBJECT, attach=True):
        supervisors = SUPERVISORS[:count]
        rows = [["Example University", name, address, ""] for name, address in supervisors]
        (cv_name, cv_path), _ = self.cv()
        imported = self.import_bundle(
            [(f"Example University_{name}.docx",
              draft_paragraphs(address, "Dear Dr,", [DECLARATION]))
             for name, address in supervisors],
            master_rows=rows, extra=[(cv_name, cv_path)])
        preparation_ids = self.core.prepare_from_documents(imported["id"])["preparation_ids"]
        for preparation_id in preparation_ids:
            if subject is not None:
                self.core.set_subject(preparation_id, subject)
            if attach:
                slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
                self.core.confirm_attachment(preparation_id, slot["id"])
        return preparation_ids

    def unready_preparation(self):
        """An active Preparation Core will not confirm: its recipient conflicts."""
        name, address = SUPERVISORS[3]
        (cv_name, cv_path), _ = self.cv()
        imported = self.import_bundle(
            [(f"Example University_{name}.docx",
              draft_paragraphs(address, "Dear Dr,", [DECLARATION]))],
            master_rows=[["Example University", name, address, ""]],
            extra=[(cv_name, cv_path)])
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        self.core.set_subject(preparation_id, SUBJECT)
        self.core.set_recipient(preparation_id, "other@nowhere.example")
        return preparation_id

    def confirm_all(self, preparation_ids):
        return [self.core.confirm(preparation_id)["id"] for preparation_id in preparation_ids]

    def outcomes(self, *values, **kwargs):
        self.mailbox = ControlledMailbox(list(values), **kwargs)
        self.core.mailbox = self.mailbox
        return self.mailbox

    def scheduling(self, *values):
        return self.outcomes(*values, allow_schedule=True)

    def scheduled_confirmations(self, preparation_ids, days=1):
        self.core.configure_plan(self.campaign["id"], timezone="UTC",
                                 windows=["MON-SUN 00:00-23:59"], spacing_minutes=1,
                                 daily_limit=len(preparation_ids), horizon_days=7)
        moment = self.core._instant()
        return [self.core.confirm(
            preparation_id,
            {"kind": "scheduled",
             "scheduled_at": (moment + timedelta(days=days + index)).isoformat(),
             "timezone": "UTC"})["id"]
            for index, preparation_id in enumerate(preparation_ids)]


class WholeRunTests(RunTestCase):
    def test_a_whole_run_completes_and_counts_only_reached_items(self):
        preparation_ids = self.ready_preparations(3)
        confirmation_ids = self.confirm_all(preparation_ids)

        run = self.core.run_batch(confirmation_ids)

        self.assertEqual(run["kind"], "immediate")
        self.assertEqual(run["state"], "completed")
        self.assertEqual(run["requested_count"], 3)
        self.assertEqual(run["executed_count"], 3)
        self.assertEqual(run["not_reached_count"], 0)
        self.assertEqual(run["summary"]["sent"], 3)
        self.assertEqual([item["outcome"] for item in run["items"]], ["sent"] * 3)
        self.assertEqual([item["sequence"] for item in run["items"]], [1, 2, 3])
        self.assertEqual([item["confirmation_id"] for item in run["items"]], confirmation_ids)
        self.assertEqual(len(self.mailbox.requests), 3)
        self.assertTrue(all(item["attempt_id"] for item in run["items"]))
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "idle")

    def test_one_run_belongs_to_one_campaign_and_one_kind(self):
        preparation_ids = self.ready_preparations(2)
        confirmation_ids = self.confirm_all(preparation_ids[:1])
        scheduled = self.scheduled_confirmations(preparation_ids[1:])[0]
        self.outcomes("sent")

        with self.assertRaisesRegex(SmartMailError, "exactly one kind"):
            self.core.run_batch(confirmation_ids + [scheduled])
        self.assertEqual(self.core.list_execution_runs(self.campaign["id"]), [])
        self.assertEqual(self.mailbox.requests, [])

        with self.assertRaisesRegex(SmartMailError, "not scheduled"):
            self.core.run_batch(confirmation_ids, kind="scheduled")

        with self.assertRaisesRegex(SmartMailError, "one Campaign"):
            self.core.run_batch(confirmation_ids + [self.other_campaign_confirmation()])
        self.assertEqual(self.core.list_execution_runs(self.campaign["id"]), [])

    def other_campaign_confirmation(self):
        """A confirmed action belonging to another Campaign, prepared the same way."""
        campaign = self.core.create_campaign("Other campaign")
        student = self.core.create_student("Other Student", "other@163.com")
        rows = [["Other University", "Dr Dana Dawn", "dana@example.edu", ""]]
        (cv_name, cv_path), _ = self.cv()
        imported = self.import_bundle(
            [("Other University_Dr Dana Dawn.docx",
              draft_paragraphs("dana@example.edu", "Dear Dr,", [DECLARATION]))],
            master_rows=rows, extra=[(cv_name, cv_path)],
            campaign=campaign["id"], student=student["id"])
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        self.core.set_subject(preparation_id, SUBJECT)
        return self.core.confirm(preparation_id)["id"]

    def test_a_disabled_kind_is_refused_before_any_external_action(self):
        preparation_ids = self.ready_preparations(2)
        confirmation_ids = self.confirm_all(preparation_ids)
        self.core.mailbox = DisabledMailbox()

        with self.assertRaisesRegex(SmartMailError, "not available"):
            self.core.run_batch(confirmation_ids)
        self.assertEqual(self.core.list_execution_runs(self.campaign["id"]), [])
        self.assertEqual(self.core.list_execution_attempts(self.campaign["id"]), [])

    def test_availability_is_reported_per_kind(self):
        self.core.mailbox = ControlledMailbox(allow_schedule=True)
        immediate = run_kind_capability(self.core, "immediate")
        scheduled = run_kind_capability(self.core, "scheduled")
        self.assertTrue(immediate["available"])
        self.assertTrue(scheduled["available"])
        self.core.mailbox = ControlledMailbox()
        self.assertTrue(run_kind_capability(self.core, "immediate")["available"])
        self.assertFalse(run_kind_capability(self.core, "scheduled")["available"])
        self.assertIn("allow_schedule",
                      run_kind_capability(self.core, "scheduled")["basis"])


class StoppedRunTests(RunTestCase):
    def test_a_failure_stops_the_run_and_records_not_reached(self):
        preparation_ids = self.ready_preparations(3)
        confirmation_ids = self.confirm_all(preparation_ids)
        self.outcomes("sent", "failed", "sent")

        run = self.core.run_batch(confirmation_ids)

        self.assertEqual(run["state"], "stopped")
        self.assertEqual(run["requested_count"], 3)
        self.assertEqual(run["executed_count"], 2)
        self.assertEqual(run["not_reached_count"], 1)
        self.assertEqual([item["outcome"] for item in run["items"]],
                         ["sent", "observed_failure", "not_reached"])
        self.assertEqual(run["summary"]["not_reached"], 1)
        self.assertEqual(len(self.mailbox.requests), 2)
        self.assertIn("failed", run["detail"] or run["items"][1]["detail"])
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "paused")

    def test_not_reached_items_run_later_and_reached_ones_never_run_again(self):
        preparation_ids = self.ready_preparations(3)
        confirmation_ids = self.confirm_all(preparation_ids)
        self.outcomes("sent", "sent", "sent")
        # A refused action stops the run without pausing the Execution Flow, so the
        # never-reached action stays eligible for the next explicitly requested run.
        self.core.set_subject(preparation_ids[1], "Content changed after confirmation")

        stopped = self.core.run_batch(confirmation_ids)
        self.assertEqual([item["outcome"] for item in stopped["items"]],
                         ["sent", "refused", "not_reached"])
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "idle")

        later = self.core.run_batch([confirmation_ids[2]])
        self.assertEqual(later["state"], "completed")
        self.assertEqual([item["outcome"] for item in later["items"]], ["sent"])
        self.assertEqual(len(self.mailbox.requests), 2)

        with self.assertRaisesRegex(SmartMailError, "already reached"):
            self.core.run_batch([confirmation_ids[1]])
        with self.assertRaisesRegex(SmartMailError, "not active"):
            self.core.run_batch([confirmation_ids[0]])
        self.assertEqual(len(self.mailbox.requests), 2)

    def test_a_refused_action_stops_the_run_without_reaching_the_rest(self):
        preparation_ids = self.ready_preparations(2)
        confirmation_ids = self.confirm_all(preparation_ids)
        self.outcomes("sent", "sent")
        self.core.set_subject(preparation_ids[1], "Content changed after confirmation")

        run = self.core.run_batch(confirmation_ids)

        self.assertEqual(run["state"], "stopped")
        self.assertEqual([item["outcome"] for item in run["items"]], ["sent", "refused"])
        self.assertEqual(len(self.mailbox.requests), 1)

    def test_a_paused_flow_refuses_a_new_run_before_any_action(self):
        preparation_ids = self.ready_preparations(2)
        confirmation_ids = self.confirm_all(preparation_ids)
        self.outcomes("unknown")
        self.core.run_batch([confirmation_ids[0]])
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "paused")

        with self.assertRaisesRegex(SmartMailError, "paused"):
            self.core.run_batch([confirmation_ids[1]])
        self.assertEqual(len(self.mailbox.requests), 1)


class RestartTests(RunTestCase):
    def test_a_restart_leaves_the_run_running_until_it_is_reconciled(self):
        preparation_ids = self.ready_preparations(2)
        confirmation_ids = self.confirm_all(preparation_ids)
        self.outcomes({"crash": "during_submission"})

        with self.assertRaises(Exception):
            self.core.run_batch(confirmation_ids)
        self.assertEqual(self.core.get_execution_run(
            self.core.list_execution_runs(self.campaign["id"])[0]["id"])["state"], "running")

        self.core.__exit__(None, None, None)
        with SmartMail(self.home, mailbox=ControlledMailbox(["sent"])) as restarted:
            run = restarted.list_execution_runs(self.campaign["id"])[0]
            self.assertEqual(run["state"], "stopped")
            self.assertEqual([item["outcome"] for item in run["items"]],
                             ["unknown_outcome", "not_reached"])
            self.assertNotEqual(run["summary"]["sent"], run["requested_count"])

    def test_reconciliation_updates_the_item_without_claiming_the_run_succeeded(self):
        preparation_ids = self.ready_preparations(1)
        confirmation_ids = self.confirm_all(preparation_ids)
        self.outcomes({"crash": "during_submission"})
        with self.assertRaises(Exception):
            self.core.run_batch(confirmation_ids)
        attempt_id = self.core.list_execution_attempts(self.campaign["id"])[0]["id"]
        run_id = self.core.list_execution_runs(self.campaign["id"])[0]["id"]

        observation = {
            "status": "complete", "mailbox_address": "student@163.com",
            "coverage": {"complete": True, "supported_scope_complete": True},
            "messages": [{
                "direction": "outbound", "folder": "sent",
                "platform_reference": "manual-sent-1", "counterpart": "alex@example.edu",
                "subject": SUBJECT, "observed_time": "2026-09-11T10:00:00+00:00",
                "status": "sent", "evidence": {"marker": "mailbox-confirmed-sent"}}],
        }
        self.core.mailbox = ControlledMailbox(observations=[observation])
        self.assertTrue(self.core.reconcile_and_continue(attempt_id)["resolved"])
        self.assertEqual(self.core.get_execution_run(run_id)["state"], "running")

        self.core.__exit__(None, None, None)
        with SmartMail(self.home, mailbox=ControlledMailbox(["sent"])) as restarted:
            run = restarted.get_execution_run(run_id)
            self.assertEqual(run["items"][0]["outcome"], "sent")
            # Resolution of the attempt never turns the stopped run into a success.
            self.assertEqual(run["state"], "completed")
            self.assertEqual(run["detail"], "")


class QueueAndHistoryTests(RunTestCase):
    def test_the_queue_reports_authorization_state_not_readiness_as_authorization(self):
        preparation_ids = self.ready_preparations(3)
        self.confirm_all(preparation_ids[:1])
        self.core.run_batch(self.confirm_all(preparation_ids[1:2]))
        unready = self.unready_preparation()

        queue = {row["preparation_id"]: row for row in
                 self.core.execution_queue(self.campaign["id"])}

        self.assertEqual(queue[preparation_ids[0]]["state"], "awaiting_execution")
        self.assertEqual(queue[preparation_ids[1]]["state"], "already_sent")
        self.assertEqual(queue[preparation_ids[2]]["state"], "ready_to_authorize")
        self.assertEqual(queue[preparation_ids[2]]["confirmation_id"], None)
        self.assertEqual(queue[unready]["state"], "not_ready")
        self.assertTrue(queue[unready]["blocking_codes"])

    def test_history_stays_inspectable_after_the_panels_empty(self):
        preparation_ids = self.ready_preparations(2)
        confirmation_ids = self.confirm_all(preparation_ids)
        run = self.core.run_batch(confirmation_ids)
        self.assertEqual(self.core.list_confirmations(self.campaign["id"]), [])

        stored = self.core.get_execution_run(run["id"])
        self.assertEqual(stored["state"], "completed")
        self.assertEqual(len(stored["items"]), 2)
        self.assertEqual([row["state"] for row in self.core.execution_queue(self.campaign["id"])],
                         ["already_sent", "already_sent"])
        self.assertEqual(len(self.core.list_execution_runs(self.campaign["id"])), 1)


class SchedulingRunTests(RunTestCase):
    def test_a_scheduled_run_places_schedules_and_never_sends_immediately(self):
        preparation_ids = self.ready_preparations(2)
        self.scheduling()
        confirmation_ids = self.scheduled_confirmations(preparation_ids)

        run = self.core.run_batch(confirmation_ids, kind="scheduled")

        self.assertEqual(run["kind"], "scheduled")
        self.assertEqual(run["state"], "completed")
        self.assertEqual([item["outcome"] for item in run["items"]],
                         ["externally_scheduled", "externally_scheduled"])
        self.assertEqual(len(self.mailbox.schedule_requests), 2)
        self.assertEqual(self.mailbox.requests, [])
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])
        self.assertEqual([row["state"] for row in self.core.execution_queue(self.campaign["id"])],
                         ["externally_scheduled", "externally_scheduled"])

    def test_a_confirmed_plan_produces_an_awaiting_execution_group_of_kind_scheduled(self):
        preparation_ids = self.ready_preparations(2)
        self.scheduling()
        self.core.configure_plan(self.campaign["id"], timezone="UTC",
                                 windows=["MON-SUN 00:00-23:59"], spacing_minutes=1,
                                 daily_limit=2, horizon_days=7)
        plan = self.core.propose_plan(self.campaign["id"])
        self.core.confirm_plan(plan["id"])

        queue = self.core.execution_queue(self.campaign["id"])
        self.assertEqual([row["state"] for row in queue], ["awaiting_execution"] * 2)
        self.assertEqual({row["confirmation_kind"] for row in queue}, {"scheduled"})

        run = self.core.run_batch([row["confirmation_id"] for row in queue], kind="scheduled")
        self.assertEqual(run["summary"]["externally_scheduled"], 2)
        with self.assertRaisesRegex(SmartMailError, "not enabled"):
            self.core.run_execution([row["confirmation_id"] for row in queue])


class BatchUiTests(RunTestCase):
    def call(self, command, **args):
        return dispatch_execution(self.core, {"command": f"execution_{command}", **args})

    def test_one_review_one_authorization_then_one_run(self):
        preparation_ids = self.ready_preparations(3)
        self.outcomes("sent", "sent", "sent")
        reviewed = self.call("review", kind="immediate", preparation_ids=preparation_ids)
        confirmations = self.call("confirm", kind="immediate",
                                  preparation_ids=preparation_ids, token=reviewed["token"])
        self.assertEqual([c["preparation_id"] for c in confirmations], preparation_ids)

        result = self.call("run", confirmation_ids=[c["id"] for c in confirmations])
        self.assertEqual(result["state"], "completed")
        self.assertEqual(result["summary"]["sent"], 3)
        self.assertEqual(len(self.mailbox.requests), 3)

    def test_a_single_confirmation_keeps_its_existing_result_shape(self):
        preparation_ids = self.ready_preparations(1)
        confirmations = self.core.confirm_preparations(preparation_ids, {"kind": "immediate"})

        result = self.call("run", confirmation_id=confirmations[0]["id"])
        self.assertEqual(result["attempts"][0]["state"], "sent")
        self.assertFalse(result["paused"])
        self.assertEqual(result["state"], "completed")

    def test_workspace_exposes_the_queue_runs_and_per_kind_availability(self):
        preparation_ids = self.ready_preparations(2)
        self.core.confirm(preparation_ids[0])
        workspace = self.call("workspace", campaign_id=self.campaign["id"])

        states = {row["preparation_id"]: row["state"] for row in workspace["queue"]}
        self.assertEqual(states[preparation_ids[0]], "awaiting_execution")
        self.assertEqual(states[preparation_ids[1]], "ready_to_authorize")
        self.assertEqual(workspace["runs"], [])
        self.assertTrue(workspace["availability"]["immediate"]["available"])
        self.assertFalse(workspace["availability"]["scheduled"]["available"])

    def test_run_history_command_returns_items_including_not_reached(self):
        preparation_ids = self.ready_preparations(2)
        confirmation_ids = self.confirm_all(preparation_ids)
        self.outcomes("sent", "failed")
        self.call("run", confirmation_ids=confirmation_ids)

        runs = self.call("runs", campaign_id=self.campaign["id"])["runs"]
        self.assertEqual([item["outcome"] for item in runs[0]["items"]],
                         ["sent", "observed_failure"])
        shown = self.call("run_show", run_id=runs[0]["id"])
        self.assertEqual(shown["state"], "stopped")


class TerminalRunTests(RunTestCase):
    def run_cli(self, *arguments, adapter=None):
        import subprocess
        import sys
        from pathlib import Path
        prefix = [sys.executable, "-m", "smartmail", "--home", str(self.home)]
        if adapter is not None:
            path = self.directory / "outcomes.json"
            path.write_text(json.dumps({"outcomes": list(adapter)}), encoding="utf-8")
            prefix += ["--adapter", "controlled", "--adapter-script", str(path)]
        return subprocess.run([*prefix, *arguments], cwd=Path(__file__).resolve().parent.parent,
                              capture_output=True, text=True, encoding="utf-8")

    def test_terminal_shell_runs_a_batch_and_keeps_its_history(self):
        preparation_ids = self.ready_preparations(2)
        confirmation_ids = self.confirm_all(preparation_ids)
        self.core.__exit__(None, None, None)

        ran = self.run_cli("execution", "batch", *confirmation_ids, adapter=["sent", "sent"])
        self.assertEqual(ran.returncode, 0, ran.stderr)
        batch = json.loads(ran.stdout)
        self.assertEqual(batch["state"], "completed")
        self.assertEqual(batch["summary"]["sent"], 2)

        listed = self.run_cli("execution", "runs", "--campaign", self.campaign["id"])
        self.assertEqual(listed.returncode, 0, listed.stderr)
        runs = json.loads(listed.stdout)
        self.assertEqual(runs[0]["state"], "completed")
        self.assertEqual(len(runs[0]["items"]), 2)

        shown = self.run_cli("execution", "run-show", runs[0]["id"])
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertEqual(json.loads(shown.stdout)["id"], runs[0]["id"])

        queued = self.run_cli("execution", "queue", "--campaign", self.campaign["id"])
        self.assertEqual(queued.returncode, 0, queued.stderr)
        self.assertEqual([row["state"] for row in json.loads(queued.stdout)],
                         ["already_sent"] * 2)

        missing = self.run_cli("execution", "run-show", "missing-run")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("not found", json.loads(missing.stderr)["error"])


if __name__ == "__main__":
    import unittest
    unittest.main()
