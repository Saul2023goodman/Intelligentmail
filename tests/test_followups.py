"""Ticket 11: Follow-up Due eligibility and separately confirmed Follow-up Actions."""

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from smartmail import SmartMail, SmartMailError
from smartmail.mailbox import ControlledMailbox
from tests.test_execution import (
    DECLARATION, DEFAULT_ROWS, DRAFT_NAME, ROOT, SUBJECT, ExecutionTestCase,
    bundle, document, draft_paragraphs, master,
)
from tests.test_replies import inbound_message, inbound_refresh

UTC = timezone.utc
SEND_AT = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)

SUBJECT_TEMPLATE = "Re: {original_subject}"
BODY_TEMPLATE = (
    "Dear {supervisor_name},\n\n"
    "I am following up on my message about PhD supervision at {institution}. "
    "My CV remains attached in the earlier thread.\n\n"
    "Yours sincerely,\n{student_name}")


class FollowUpTestCase(ExecutionTestCase):
    def configure_rule(self, *, delay_days=3, maximum_count=2,
                       subject_template=SUBJECT_TEMPLATE, body_template=BODY_TEMPLATE):
        return self.core.configure_follow_up_rule(
            self.campaign["id"], delay_days=delay_days, maximum_count=maximum_count,
            subject_template=subject_template, body_template=body_template)

    def send_initial_at(self, moment=SEND_AT):
        self.at(moment)
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        self.core.run_execution([confirmation["id"]])
        return self.core.get_preparation(preparation["id"])

    def observe_reply(self, observed_at="2026-09-18T09:00:00+00:00", **message_kwargs):
        message_kwargs.setdefault("observed_time", observed_at)
        message = inbound_message(**message_kwargs)
        self.mailbox = ControlledMailbox(
            observations=[inbound_refresh([message], observed_at=observed_at)])
        self.core.mailbox = self.mailbox
        return self.core.refresh_mailbox(self.student["id"])

    def state_for(self, task_id):
        return next(item for item in self.core.follow_up_status(self.campaign["id"])
                    if item["task_id"] == task_id)

    def revised_source(self, body=("Revised follow-up content.",)):
        """A second import's Source Material describing the same Outreach Task."""
        imported = self.core.import_master(
            self.campaign["id"], self.student["id"],
            bundle(self.directory / "revised-bundle.zip", [
                ("master.xlsx", master(self.directory / "master-revised.xlsx", DEFAULT_ROWS)),
                (DRAFT_NAME, document(
                    self.directory / "draft-revised.docx",
                    draft_paragraphs("alex@example.edu", "Dear Dr Green,", list(body)))),
            ]))
        return next(s for s in self.core.get_import(imported["id"])["sources"]
                    if s["name"] == DRAFT_NAME)


class FollowUpRuleTests(FollowUpTestCase):
    def test_an_unconfigured_campaign_does_not_invent_follow_up_rules(self):
        self.send_initial_at()
        status = self.core.follow_up_status(self.campaign["id"])
        self.assertEqual(status[0]["state"], "rule_not_configured")
        self.assertFalse(status[0]["eligible"])

    def test_rule_validation_rejects_bad_limits_and_unknown_template_fields(self):
        with self.assertRaises(SmartMailError):
            self.core.configure_follow_up_rule(self.campaign["id"], delay_days=-1,
                                               maximum_count=2)
        with self.assertRaises(SmartMailError):
            self.core.configure_follow_up_rule(self.campaign["id"], delay_days=3,
                                               maximum_count=0)
        with self.assertRaises(SmartMailError):
            self.core.configure_follow_up_rule(
                self.campaign["id"], delay_days=3, maximum_count=2,
                subject_template="Re: {mysterious_field}")
        self.assertIsNone(self.core.get_follow_up_rule(self.campaign["id"]))

    def test_rule_persists_and_survives_restart(self):
        rule = self.configure_rule()
        self.assertEqual(rule["delay_days"], 3)
        self.assertEqual(rule["maximum_count"], 2)
        self.core.__exit__(None, None, None)
        with SmartMail(self.home) as restarted:
            self.assertEqual(restarted.get_follow_up_rule(self.campaign["id"]), rule)


class FollowUpEligibilityTests(FollowUpTestCase):
    def test_no_initial_send_means_not_eligible(self):
        self.configure_rule()
        preparation, _ = self.ready_preparation()
        state = self.state_for(preparation["task_id"])
        self.assertEqual(state["state"], "no_initial_send")
        self.assertFalse(state["eligible"])

    def test_eligibility_waits_for_the_configured_delay_then_becomes_due(self):
        preparation = self.send_initial_at()
        self.configure_rule(delay_days=3)

        self.at(SEND_AT + timedelta(days=2))
        waiting = self.state_for(preparation["task_id"])
        self.assertEqual(waiting["state"], "waiting")
        self.assertFalse(waiting["eligible"])
        self.assertEqual(waiting["due_at"],
                         (SEND_AT + timedelta(days=3)).isoformat())

        self.at(SEND_AT + timedelta(days=3, minutes=1))
        due = self.state_for(preparation["task_id"])
        self.assertEqual(due["state"], "due")
        self.assertTrue(due["eligible"])
        self.assertEqual(due["next_sequence"], 1)

    def test_an_ordinary_reply_stops_eligibility_without_classification(self):
        preparation = self.send_initial_at()
        self.configure_rule()
        self.at(SEND_AT + timedelta(days=4))
        self.assertEqual(self.state_for(preparation["task_id"])["state"], "due")

        self.observe_reply(observed_at="2026-09-18T09:00:00+00:00")

        state = self.state_for(preparation["task_id"])
        self.assertEqual(state["state"], "ordinary_reply_received")
        self.assertFalse(state["eligible"])
        self.assertEqual(state["counts"]["ordinary_replies"], 1)
        self.assertEqual(state["counts"]["automatic_replies"], 0)

    def test_a_recognized_automatic_reply_does_not_stop_eligibility(self):
        preparation = self.send_initial_at()
        self.configure_rule()
        self.at(SEND_AT + timedelta(days=4))

        self.observe_reply(subject=f"Out of Office: Re: {SUBJECT}",
                           observed_at="2026-09-18T09:00:00+00:00")

        state = self.state_for(preparation["task_id"])
        self.assertEqual(state["state"], "due")
        self.assertTrue(state["eligible"])
        self.assertEqual(state["counts"]["automatic_replies"], 1)
        self.assertEqual(state["counts"]["ordinary_replies"], 0)

    def test_an_unresolved_ambiguous_association_never_silently_drives_eligibility(self):
        preparation = self.send_initial_at()
        second_campaign = self.core.create_campaign("2028 outreach")
        second_bundle = bundle(self.directory / "bundle-2.zip", [
            ("master.xlsx", master(self.directory / "master-2.xlsx", DEFAULT_ROWS)),
            (DRAFT_NAME, document(
                self.directory / "draft-2.docx",
                draft_paragraphs("alex@example.edu", "Dear Dr Green,", [DECLARATION]))),
        ])
        second_import = self.core.import_master(
            second_campaign["id"], self.student["id"], second_bundle)
        self.core.set_subject(
            self.core.prepare_from_documents(second_import["id"])["preparation_ids"][0],
            "Other topic")
        self.configure_rule()
        self.at(SEND_AT + timedelta(days=4))

        self.observe_reply(subject="Re: unrelated thread",
                           observed_at="2026-09-18T09:00:00+00:00")

        state = self.state_for(preparation["task_id"])
        self.assertEqual(state["state"], "reply_review_required")
        self.assertFalse(state["eligible"])
        self.assertEqual(state["counts"]["ambiguous"], 1)

    def test_maximum_count_is_enforced_across_prepared_and_sent_follow_ups(self):
        preparation = self.send_initial_at()
        self.configure_rule(delay_days=1, maximum_count=1)
        self.at(SEND_AT + timedelta(days=2))
        prepared = self.core.prepare_follow_ups(self.campaign["id"])
        self.assertEqual(len(prepared), 1)
        self.assertEqual(self.state_for(preparation["task_id"])["state"], "follow_up_open")
        self.assertEqual(self.state_for(preparation["task_id"])["next_sequence"], 2)

        # The single allowed Action stays open until executed; a second Action
        # is never stacked in parallel, however much time passes.
        self.at(SEND_AT + timedelta(days=10))
        self.assertEqual(self.state_for(preparation["task_id"])["state"], "follow_up_open")
        self.assertEqual(self.core.prepare_follow_ups(self.campaign["id"]), [])


class PreparedFollowUpTests(FollowUpTestCase):
    def test_a_due_task_with_a_template_gets_a_linked_ready_follow_up_preparation(self):
        preparation = self.send_initial_at()
        initial_sent = self.core.list_sent_records(self.campaign["id"])[0]
        self.configure_rule()
        self.at(SEND_AT + timedelta(days=4))

        actions = self.core.prepare_follow_ups(self.campaign["id"])

        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action["status"], "prepared")
        self.assertEqual(action["sequence"], 1)
        self.assertEqual(action["follows_sent_record_id"], initial_sent["id"])
        follow_up = self.core.get_preparation(action["preparation_id"])
        self.assertEqual(follow_up["action_kind"], "follow_up")
        self.assertEqual(follow_up["linked_sent_record_id"], initial_sent["id"])
        self.assertEqual(follow_up["task_id"], preparation["task_id"])
        self.assertEqual(follow_up["recipient"], "alex@example.edu")
        self.assertEqual(follow_up["subject"], f"Re: {SUBJECT}")
        self.assertIn("Example University", follow_up["body"])
        self.assertTrue(follow_up["ready"])
        self.assertEqual(
            self.core.check_duplicate(follow_up["id"])["finding"], "linked_follow_up")
        self.assertEqual(self.state_for(preparation["task_id"])["state"], "follow_up_open")

    def test_a_due_task_without_a_template_is_marked_due_without_invented_content(self):
        preparation = self.send_initial_at()
        self.configure_rule(subject_template="", body_template="")
        self.at(SEND_AT + timedelta(days=4))

        actions = self.core.prepare_follow_ups(self.campaign["id"])

        self.assertEqual(len(actions), 1)
        action = actions[0]
        self.assertEqual(action["status"], "due_for_preparation")
        self.assertIsNone(action["preparation_id"])
        self.assertTrue(action["detail"])
        # No follow-up Preparation content was invented; only the initial one exists.
        self.assertEqual(
            [p["id"] for p in self.core.list_preparations(self.campaign["id"])],
            [preparation["id"]])

    def test_operator_prepares_content_for_a_due_action_from_source_material(self):
        self.send_initial_at()
        self.configure_rule(subject_template="", body_template="")
        self.at(SEND_AT + timedelta(days=4))
        action = self.core.prepare_follow_ups(self.campaign["id"])[0]
        source = next(s for s in self.core.get_import(
            self.core.list_imports(self.campaign["id"])[0]["id"])["sources"]
            if s["name"] == DRAFT_NAME)

        prepared = self.core.prepare_follow_up_action(action["id"], source_id=source["id"])

        self.assertEqual(prepared["status"], "prepared")
        follow_up = self.core.get_preparation(prepared["preparation_id"])
        self.assertEqual(follow_up["action_kind"], "follow_up")
        self.assertIn("Dear Dr Green,", follow_up["body"])

    def test_rewriting_a_follow_up_preparation_keeps_the_linked_action_chain(self):
        preparation = self.send_initial_at()
        initial_sent = self.core.list_sent_records(self.campaign["id"])[0]
        self.configure_rule(maximum_count=1)
        self.at(SEND_AT + timedelta(days=4))
        action = self.core.prepare_follow_ups(self.campaign["id"])[0]

        revised = self.revised_source(["Revised follow-up content."])
        fresh = self.core.rewrite(action["preparation_id"], source_id=revised["id"])

        # The replacement stays a linked Follow-up Action bound to the same anchor.
        self.assertEqual(fresh["action_kind"], "follow_up")
        self.assertEqual(fresh["linked_sent_record_id"], initial_sent["id"])
        self.assertTrue(any(change["code"] == "follow_up_linked"
                            for change in fresh["transformations"]))
        self.assertEqual(
            self.core.get_follow_up_action(action["id"])["preparation_id"], fresh["id"])
        self.assertEqual(
            self.core.check_duplicate(fresh["id"])["finding"], "linked_follow_up")

        # It still needs its own Confirmation and executes as a follow-up.
        self.core.set_subject(fresh["id"], f"Re: {SUBJECT}")
        confirmation = self.core.confirm(fresh["id"])
        self.core.mailbox = ControlledMailbox(["sent"])
        result = self.core.run_execution([confirmation["id"]])
        self.assertFalse(result["paused"])
        self.assertEqual(
            self.core.get_follow_up_action(action["id"])["status"], "sent")
        records = self.core.list_sent_records(self.campaign["id"])
        follow_up_record = next(record for record in records if record["id"] != initial_sent["id"])
        self.assertEqual(follow_up_record["action_kind"], "follow_up")
        self.assertEqual(follow_up_record["follows_sent_record_id"], initial_sent["id"])
        self.assertEqual(self.state_for(preparation["task_id"])["state"], "maximum_reached")


class FollowUpSafeguardTests(FollowUpTestCase):
    def test_unconfirmed_follow_up_is_refused_and_submits_nothing(self):
        self.send_initial_at()
        self.configure_rule()
        self.at(SEND_AT + timedelta(days=4))
        self.core.prepare_follow_ups(self.campaign["id"])

        fresh = ControlledMailbox()
        self.core.mailbox = fresh
        with self.assertRaises(SmartMailError):
            self.core.run_execution([])
        self.assertEqual(fresh.requests, [])
        attempts = self.core.list_execution_attempts(self.campaign["id"])
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["state"], "sent")

    def test_confirming_a_follow_up_after_an_ordinary_reply_is_refused(self):
        self.send_initial_at()
        self.configure_rule()
        self.at(SEND_AT + timedelta(days=4))
        action = self.core.prepare_follow_ups(self.campaign["id"])[0]
        confirmation = self.core.confirm(action["preparation_id"])
        self.assertEqual(confirmation["status"], "active")

        self.observe_reply(observed_at="2026-09-19T10:00:00+00:00")

        with self.assertRaises(SmartMailError):
            self.core.confirm(action["preparation_id"])

    def test_a_reply_arriving_after_confirmation_pauses_without_an_obsolete_send(self):
        self.send_initial_at()
        self.configure_rule()
        self.at(SEND_AT + timedelta(days=4))
        action = self.core.prepare_follow_ups(self.campaign["id"])[0]
        confirmation = self.core.confirm(action["preparation_id"])

        reply_at = SEND_AT + timedelta(days=5, hours=1)
        self.at(reply_at)
        self.observe_reply(observed_at=reply_at.isoformat())
        result = self.core.run_execution([confirmation["id"]])

        self.assertTrue(result["paused"])
        self.assertEqual(result["flow"]["reason"], "new_associated_reply")
        self.assertEqual(result["attempts"], [])
        self.assertEqual(self.mailbox.requests, [])
        self.assertEqual(self.core.get_confirmation(confirmation["id"])["status"], "active")
        self.assertEqual(
            [attempt for attempt in self.core.list_execution_attempts(self.campaign["id"])
             if attempt["preparation_id"] == action["preparation_id"]], [])
        with self.assertRaises(SmartMailError):
            self.core.run_execution([confirmation["id"]])

    def test_rewrite_releases_the_pause_but_the_reply_still_blocks_confirmation(self):
        self.send_initial_at()
        self.configure_rule()
        self.at(SEND_AT + timedelta(days=4))
        action = self.core.prepare_follow_ups(self.campaign["id"])[0]
        confirmation = self.core.confirm(action["preparation_id"])
        reply_at = SEND_AT + timedelta(days=5, hours=1)
        self.at(reply_at)
        self.observe_reply(observed_at=reply_at.isoformat())
        self.assertTrue(self.core.run_execution([confirmation["id"]])["paused"])

        revised = self.revised_source()
        fresh = self.core.rewrite(action["preparation_id"], source_id=revised["id"])

        self.assertEqual(fresh["action_kind"], "follow_up")
        self.assertEqual(
            self.core.get_follow_up_action(action["id"])["preparation_id"], fresh["id"])
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"],
                         "idle")
        # The reliable Ordinary Reply was not resolved away; the replacement still
        # cannot be confirmed while no-reply eligibility is stopped.
        self.core.set_subject(fresh["id"], f"Re: {SUBJECT}")
        with self.assertRaisesRegex(SmartMailError, "Ordinary Reply is associated"):
            self.core.confirm(fresh["id"])

    def test_confirmed_follow_up_executes_through_the_controlled_adapter_and_links(self):
        self.send_initial_at()
        initial_sent = self.core.list_sent_records(self.campaign["id"])[0]
        self.configure_rule()
        self.at(SEND_AT + timedelta(days=4))
        action = self.core.prepare_follow_ups(self.campaign["id"])[0]
        confirmation = self.core.confirm(action["preparation_id"])

        result = self.core.run_execution([confirmation["id"]])

        self.assertFalse(result["paused"])
        self.assertEqual(len(self.mailbox.requests), 2)
        self.assertEqual(self.mailbox.requests[-1]["subject"], f"Re: {SUBJECT}")
        follow_up_record = next(
            record for record in self.core.list_sent_records(self.campaign["id"])
            if record["id"] != initial_sent["id"])
        self.assertEqual(follow_up_record["action_kind"], "follow_up")
        self.assertEqual(follow_up_record["follows_sent_record_id"], initial_sent["id"])
        self.assertEqual(follow_up_record["subject"], f"Re: {SUBJECT}")

    def test_chained_follow_ups_honor_delay_and_the_action_survives_restart(self):
        preparation = self.send_initial_at()
        self.configure_rule(delay_days=2, maximum_count=2)
        self.at(SEND_AT + timedelta(days=3))
        first = self.core.prepare_follow_ups(self.campaign["id"])[0]
        first_confirmation = self.core.confirm(first["preparation_id"])
        self.core.run_execution([first_confirmation["id"]])
        self.assertEqual(self.state_for(preparation["task_id"])["state"], "waiting")

        self.at(SEND_AT + timedelta(days=6))
        self.assertEqual(self.state_for(preparation["task_id"])["state"], "due")
        second = self.core.prepare_follow_ups(self.campaign["id"])[0]
        self.assertEqual(second["sequence"], 2)
        second_confirmation = self.core.confirm(second["preparation_id"])
        self.core.run_execution([second_confirmation["id"]])
        self.assertEqual(self.state_for(preparation["task_id"])["state"], "maximum_reached")

        self.core.__exit__(None, None, None)
        with SmartMail(self.home) as restarted:
            actions = restarted.list_follow_up_actions(self.campaign["id"])
            self.assertEqual([a["sequence"] for a in actions], [1, 2])
            self.assertTrue(all(a["status"] == "sent" for a in actions))
            state = next(item for item in restarted.follow_up_status(self.campaign["id"])
                         if item["task_id"] == preparation["task_id"])
            self.assertEqual(state["state"], "maximum_reached")


class FollowUpAutomationTests(FollowUpTestCase):
    def enable_automation(self, **overrides):
        values = {
            "delay_days": 3,
            "maximum_count": 2,
            "subject_template": SUBJECT_TEMPLATE,
            "body_template": BODY_TEMPLATE,
            "enabled": True,
            "timezone_name": "Asia/Shanghai",
            "send_time": "09:30",
        }
        values.update(overrides)
        return self.core.configure_follow_up_rule(self.campaign["id"], **values)

    def test_enabled_configuration_is_a_versioned_standing_confirmation(self):
        self.at(SEND_AT)
        rule = self.enable_automation()

        self.assertTrue(rule["enabled"])
        self.assertEqual(rule["revision"], 1)
        self.assertEqual(rule["confirmed_at"], SEND_AT.isoformat())
        self.assertEqual(len(rule["policy_digest"]), 64)
        unchanged = self.enable_automation()
        self.assertEqual(unchanged["revision"], 1)
        changed = self.core.configure_follow_up_rule(
            self.campaign["id"], send_time="10:00")
        self.assertEqual(changed["revision"], 2)
        self.assertEqual(changed["send_time"], "10:00")

    def test_enabling_requires_deterministic_content_and_time(self):
        with self.assertRaisesRegex(SmartMailError, "subject and body"):
            self.core.configure_follow_up_rule(
                self.campaign["id"], delay_days=3, maximum_count=2, enabled=True,
                send_time="09:00")
        with self.assertRaisesRegex(SmartMailError, "exact local send time"):
            self.core.configure_follow_up_rule(
                self.campaign["id"], delay_days=3, maximum_count=2, enabled=True,
                subject_template=SUBJECT_TEMPLATE, body_template=BODY_TEMPLATE)

    def test_due_automation_enters_ready_pool_once_without_executing(self):
        initial = self.send_initial_at()
        self.at(SEND_AT + timedelta(hours=1))
        rule = self.enable_automation(delay_days=1, send_time="09:00")
        self.at(SEND_AT + timedelta(days=2))

        result = self.core.process_follow_up_automation(self.campaign["id"])

        self.assertEqual(result["state"], "ready_pool")
        self.assertEqual(len(result["created_action_ids"]), 1)
        self.assertEqual(len(result["ready_preparation_ids"]), 1)
        action = self.core.get_follow_up_action(result["created_action_ids"][0])
        self.assertEqual(action["status"], "prepared")
        self.assertEqual(action["policy_digest"], rule["policy_digest"])
        self.assertEqual(self.core.list_confirmations(self.campaign["id"]), [])
        ready = next(row for row in self.core.execution_queue(self.campaign["id"])
                     if row["preparation_id"] == action["preparation_id"])
        self.assertEqual(ready["state"], "ready_to_authorize")
        self.assertEqual(len(self.mailbox.requests), 1)
        self.assertEqual(self.state_for(initial["task_id"])["state"], "follow_up_open")

        again = self.core.process_follow_up_automation(self.campaign["id"])
        self.assertEqual(again["created_action_ids"], [])
        self.assertEqual(again["ready_preparation_ids"], [])
        self.assertEqual(len(self.mailbox.requests), 1)

    def test_trigger_never_depends_on_or_touches_mailbox_execution(self):
        self.send_initial_at()
        self.enable_automation(delay_days=1)
        fresh = ControlledMailbox(default="failed")
        self.core.mailbox = fresh
        self.at(SEND_AT + timedelta(days=2))

        result = self.core.process_follow_up_automation(self.campaign["id"])

        self.assertEqual(result["state"], "ready_pool")
        self.assertEqual(len(result["ready_preparation_ids"]), 1)
        self.assertEqual(
            self.core.get_follow_up_action(result["created_action_ids"][0])["status"],
            "prepared")
        self.assertEqual(fresh.requests, [])
        self.assertEqual(len(self.core.list_execution_attempts(self.campaign["id"])), 1)

    def test_ordinary_reply_prevents_automatic_preparation_and_execution(self):
        preparation = self.send_initial_at()
        self.enable_automation(delay_days=1)
        self.at(SEND_AT + timedelta(days=2))
        self.observe_reply(observed_at=self.moment.isoformat())

        result = self.core.process_follow_up_automation(self.campaign["id"])

        self.assertEqual(result["state"], "idle")
        self.assertEqual(result["created_action_ids"], [])
        self.assertEqual(result["ready_preparation_ids"], [])
        self.assertEqual(self.state_for(preparation["task_id"])["state"],
                         "ordinary_reply_received")


class FollowUpTerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state-terminal"

    def run_cli(self, *arguments, adapter=None, now=None):
        prefix = [sys.executable, "-m", "smartmail", "--home", str(self.home)]
        if now is not None:
            prefix += ["--now", now]
        if adapter is not None:
            prefix += ["--adapter", "controlled", "--adapter-script", str(adapter)]
        return subprocess.run(
            [*prefix, *arguments], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def build_sent_store(self):
        campaign = json.loads(self.run_cli("campaign", "create", "2027 outreach").stdout)
        student = json.loads(self.run_cli(
            "student", "create", "Test Student", "--mailbox", "student@163.com").stdout)
        members = [
            ("master.xlsx", master(self.directory / "master.xlsx", DEFAULT_ROWS)),
            (DRAFT_NAME, document(self.directory / "draft.docx",
                                  draft_paragraphs("alex@example.edu",
                                                   "Dear Dr Green,", [DECLARATION]))),
            ("Test Student - CV.docx",
             document(self.directory / "cv.docx", ["Test Student", "E-mail: student@163.com"])),
        ]
        imported = json.loads(self.run_cli(
            "import", str(bundle(self.directory / "bundle.zip", members)),
            "--campaign", campaign["id"], "--student", student["id"]).stdout)
        preparation_id = json.loads(
            self.run_cli("prepare", "--import", imported["id"]).stdout)["preparation_ids"][0]
        self.run_cli("preparation", "set-subject", preparation_id, SUBJECT)
        slot = json.loads(self.run_cli(
            "preparation", "show", preparation_id).stdout)["attachment_slots"][0]
        self.run_cli("preparation", "confirm", preparation_id, "--slot", slot["id"])
        confirmed = json.loads(self.run_cli("confirmation", "confirm", preparation_id).stdout)
        outcomes = self.directory / "outcomes.json"
        outcomes.write_text(json.dumps({"outcomes": ["sent"]}), encoding="utf-8")
        self.run_cli("execution", "run", confirmed[0]["id"], adapter=outcomes,
                     now="2026-09-15T09:00:00+00:00")
        return campaign, student, outcomes

    def test_configure_prepare_confirm_and_send_a_follow_up_through_the_shell(self):
        campaign, student, outcomes = self.build_sent_store()
        configured = self.run_cli(
            "followup", "configure", "--campaign", campaign["id"],
            "--delay-days", "3", "--max", "2",
            "--subject-template", SUBJECT_TEMPLATE,
            "--body-template", BODY_TEMPLATE)
        self.assertEqual(configured.returncode, 0, configured.stderr)

        status = json.loads(self.run_cli(
            "followup", "status", "--campaign", campaign["id"],
            now="2026-09-18T09:00:00+00:00").stdout)
        self.assertEqual(status[0]["state"], "due")

        actions = json.loads(self.run_cli(
            "followup", "prepare", "--campaign", campaign["id"],
            now="2026-09-18T09:00:00+00:00").stdout)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["status"], "prepared")
        listed = json.loads(self.run_cli(
            "followup", "list", "--campaign", campaign["id"]).stdout)
        self.assertEqual([a["id"] for a in listed], [actions[0]["id"]])
        shown = json.loads(self.run_cli("followup", "show", actions[0]["id"]).stdout)
        self.assertEqual(shown["id"], actions[0]["id"])

        confirmed = json.loads(self.run_cli(
            "confirmation", "confirm", actions[0]["preparation_id"]).stdout)
        ran = self.run_cli("execution", "run", confirmed[0]["id"], adapter=outcomes,
                           now="2026-09-18T09:00:00+00:00")
        self.assertEqual(ran.returncode, 0, ran.stderr)
        self.assertFalse(json.loads(ran.stdout)["paused"])
        sent = json.loads(self.run_cli("sent", "list", "--campaign", campaign["id"]).stdout)
        self.assertEqual(len(sent), 2)
        self.assertTrue(any(record["action_kind"] == "follow_up" for record in sent))

    def test_an_action_prepared_without_templates_persists_between_processes(self):
        campaign, _student, _outcomes = self.build_sent_store()
        self.assertEqual(self.run_cli(
            "followup", "configure", "--campaign", campaign["id"],
            "--delay-days", "3", "--max", "2").returncode, 0)

        prepared = self.run_cli(
            "followup", "prepare", "--campaign", campaign["id"],
            now="2026-09-18T09:00:00+00:00")
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        action_id = json.loads(prepared.stdout)[0]["id"]

        # A fresh process must still see the committed due-for-preparation Action.
        listed = json.loads(self.run_cli("followup", "list", "--campaign", campaign["id"]).stdout)
        self.assertEqual([a["id"] for a in listed], [action_id])
        shown = json.loads(self.run_cli("followup", "show", action_id).stdout)
        self.assertEqual(shown["status"], "due_for_preparation")
        self.assertFalse(shown["preparation_id"])
        self.assertIn("Source Material", shown["detail"])


if __name__ == "__main__":
    unittest.main()
