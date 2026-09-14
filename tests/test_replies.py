"""Ticket 11: deterministic reply association and Recognized Automatic Replies."""

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

SEND_AT = datetime(2026, 9, 14, 9, 0, tzinfo=timezone.utc)
REPLY_AT = "2026-09-14T12:30:00+00:00"


def inbound_message(counterpart="alex@example.edu", subject=f"Re: {SUBJECT}",
                    reference="reply-1", observed_time=REPLY_AT, evidence=None,
                    status="received", ambiguity=""):
    """A persisted read-only inbound observation from the controlled mailbox."""
    return {
        "direction": "inbound", "folder": "inbox", "platform_reference": reference,
        "counterpart": counterpart, "subject": subject,
        "observed_time": observed_time, "status": status, "ambiguity": ambiguity,
        "evidence": evidence if evidence is not None else {
            "aria_label": f"{subject} 发件人 ： {counterpart}"},
    }


def inbound_refresh(messages, mailbox="student@163.com", observed_at=REPLY_AT):
    return {
        "status": "complete",
        "mailbox_address": mailbox,
        "observed_at": observed_at,
        "detail": "controlled inbound observation",
        "coverage": {
            "complete": False, "supported_scope_complete": True,
            "folders": [{"folder": "inbox", "declared_total": len(messages),
                         "ids_enumerated": len(messages), "enumeration_complete": True,
                         "detail_complete": True, "complete": True}],
        },
        "messages": messages,
    }


class ReplyAssociationTestCase(ExecutionTestCase):
    def observe(self, messages, *, observed_at=REPLY_AT):
        if isinstance(messages, dict):
            messages = [messages]
        self.mailbox = ControlledMailbox(
            observations=[inbound_refresh(messages, observed_at=observed_at)])
        self.core.mailbox = self.mailbox
        return self.core.refresh_mailbox(self.student["id"])

    def send_initial(self, subject=SUBJECT):
        preparation, _ = self.ready_preparation(subject=subject)
        confirmation = self.core.confirm(preparation["id"], confirmed_at=SEND_AT)
        self.core.run_execution([confirmation["id"]])
        return self.core.get_preparation(preparation["id"])


class ReliableReplyTests(ReplyAssociationTestCase):
    def test_a_reply_from_a_known_supervisor_on_the_send_thread_is_associated(self):
        preparation = self.send_initial()

        refreshed = self.observe(inbound_message())
        result = self.core.list_reply_associations(self.campaign["id"])

        self.assertEqual(len(result), 1)
        association = result[0]
        self.assertEqual(association["status"], "associated")
        self.assertEqual(association["reply_kind"], "ordinary")
        self.assertEqual(association["task_id"], preparation["task_id"])
        self.assertEqual(association["student_id"], self.student["id"])
        self.assertEqual(association["observation"]["counterpart"], "alex@example.edu")
        self.assertIn("known_supervisor_address", association["basis"])
        self.assertTrue(association["evidence_coverage"]["timing_available"])
        self.assertIn("message_body_html",
                      " ".join(association["evidence_coverage"]["excluded_fields"]))
        findings = {f["finding"]: f for f in refreshed["reconciliation"]["findings"]}
        self.assertIn("associated_reply", findings)
        self.assertEqual(findings["associated_reply"]["local_kind"], "reply_association")
        self.assertEqual(findings["associated_reply"]["local_id"], association["id"])
        self.assertEqual(self.core.get_reply_association(association["id"]), association)

    def test_a_reply_before_any_outreach_thread_is_not_silently_associated(self):
        preparation, _ = self.ready_preparation()

        self.observe(inbound_message())

        associations = self.core.list_reply_associations(self.campaign["id"])
        ambiguous = [a for a in associations if a["status"] == "ambiguous"]
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0]["task_id"], None)
        self.assertIn(preparation["task_id"], ambiguous[0]["candidate_task_ids"])
        self.assertEqual(ambiguous[0]["basis"], "no_open_outreach_thread")

    def test_a_message_observed_before_the_send_is_not_associated_on_address_alone(self):
        preparation = self.send_initial()

        self.observe(inbound_message(
            subject="A different unrelated thread",
            observed_time="2026-09-10T08:00:00+00:00", reference="early"))

        ambiguous = self.core.list_reply_associations(self.campaign["id"], status="ambiguous")
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0]["basis"], "no_open_outreach_thread")
        self.assertEqual(ambiguous[0]["candidate_task_ids"], [preparation["task_id"]])

    def test_an_off_thread_message_without_usable_timing_needs_review(self):
        preparation = self.send_initial()

        self.observe(inbound_message(
            subject="A different unrelated thread",
            observed_time="2026年9月18日 17:30", reference="localized"))

        ambiguous = self.core.list_reply_associations(self.campaign["id"], status="ambiguous")
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0]["candidate_task_ids"], [preparation["task_id"]])
        self.assertFalse(ambiguous[0]["evidence_coverage"]["timing_available"])

    def test_a_message_from_an_unknown_address_stays_unassociated(self):
        self.send_initial()

        refreshed = self.observe(inbound_message(
            counterpart="stranger@example.edu", reference="reply-x"))

        self.assertEqual(self.core.list_reply_associations(self.campaign["id"]), [])
        findings = [f["finding"] for f in refreshed["reconciliation"]["findings"]]
        self.assertIn("unassociated_inbound", findings)

    def test_a_chinese_localized_observed_time_is_a_recorded_coverage_limitation(self):
        preparation = self.send_initial()

        self.observe(inbound_message(observed_time="2026年9月14日 20:30"))

        association = self.core.list_reply_associations(self.campaign["id"])[0]
        self.assertEqual(association["status"], "associated")
        self.assertFalse(association["evidence_coverage"]["timing_available"])
        self.assertTrue(any("observed time" in limitation
                            for limitation in association["evidence_coverage"]["limitations"]))


class AutomaticReplyTests(ReplyAssociationTestCase):
    def assert_automatic(self, message, expected_rule):
        self.send_initial()
        refreshed = self.observe(message)
        association = self.core.list_reply_associations(self.campaign["id"])[0]
        self.assertEqual(association["status"], "associated")
        self.assertEqual(association["reply_kind"], "automatic")
        self.assertEqual(association["matched_rule"], expected_rule)
        self.assertTrue(association["evidence"]["matched_rule_detail"])
        self.assertEqual(refreshed["reconciliation"]["summary"]["automatic_replies"], 1)
        self.assertEqual(refreshed["reconciliation"]["summary"]["associated_replies"], 0)
        return association

    def test_an_english_out_of_office_subject_is_a_recognized_automatic_reply(self):
        self.assert_automatic(
            inbound_message(subject=f"Out of Office: Re: {SUBJECT}"), "subject_marker")

    def test_a_chinese_automatic_reply_subject_is_recognized(self):
        self.assert_automatic(
            inbound_message(subject=f"自动回复：{SUBJECT}"), "subject_marker")

    def test_an_auto_submitted_header_marker_is_recognized_from_metadata(self):
        self.assert_automatic(inbound_message(
            subject=f"Re: {SUBJECT}",
            evidence={"auto_submitted": "auto-replied"}), "auto_submitted_header")

    def test_automatic_replies_remain_separately_inspectable_after_restart(self):
        association = self.assert_automatic(
            inbound_message(subject=f"Auto: {SUBJECT}"), "subject_marker")

        self.core.__exit__(None, None, None)
        with SmartMail(self.home) as restarted:
            persisted = restarted.get_reply_association(association["id"])
            self.assertEqual(persisted["reply_kind"], "automatic")
            self.assertEqual(persisted["matched_rule"], "subject_marker")

    def test_an_unmarked_message_is_ordinary_without_semantic_guessing(self):
        self.send_initial()
        self.observe(inbound_message(subject=f"Re: {SUBJECT}", evidence={
            "aria_label": "anything at all; body HTML is never observed"}))
        association = self.core.list_reply_associations(self.campaign["id"])[0]
        self.assertEqual(association["reply_kind"], "ordinary")
        self.assertEqual(association["matched_rule"], "")


class AmbiguousResolutionTests(ReplyAssociationTestCase):
    def test_two_campaign_tasks_for_one_supervisor_require_thread_resolution(self):
        first = self.send_initial()
        second_campaign = self.core.create_campaign("2028 outreach")
        second_members = [
            ("master.xlsx", master(self.directory / "master-2.xlsx", DEFAULT_ROWS)),
            (DRAFT_NAME, document(
                self.directory / "draft-2.docx",
                draft_paragraphs("alex@example.edu", "Dear Dr Green,", [DECLARATION]))),
        ]
        second_bundle = bundle(self.directory / "bundle-2.zip", second_members)
        second_import = self.core.import_master(
            second_campaign["id"], self.student["id"], second_bundle)
        second_preparation_id = self.core.prepare_from_documents(
            second_import["id"])["preparation_ids"][0]
        self.core.set_subject(second_preparation_id, "A different subject")
        second_task_id = self.core.get_preparation(second_preparation_id)["task_id"]
        self.assertNotEqual(first["task_id"], second_task_id)

        self.observe(inbound_message(subject=f"Re: {SUBJECT}"))

        ambiguous = self.core.list_reply_associations(status="ambiguous")
        self.assertEqual(len(ambiguous), 0, "subject marker identifies the sent task")
        associated = self.core.list_reply_associations(self.campaign["id"])[0]
        self.assertEqual(associated["task_id"], first["task_id"])

        self.observe(inbound_message(subject="Re: A brand new topic", reference="reply-2"))
        pending = self.core.list_reply_associations(status="ambiguous")
        self.assertEqual(len(pending), 1)
        self.assertEqual(set(pending[0]["candidate_task_ids"]),
                         {first["task_id"], second_task_id})
        self.assertEqual(pending[0]["basis"], "multiple_candidate_tasks")

    def test_operator_pins_an_ambiguous_reply_to_a_candidate_task(self):
        self.ready_preparation()
        self.observe(inbound_message())
        ambiguous = self.core.list_reply_associations(status="ambiguous")[0]

        resolved = self.core.resolve_reply_association(
            ambiguous["id"], ambiguous["candidate_task_ids"][0])

        self.assertEqual(resolved["status"], "associated")
        self.assertEqual(resolved["reply_kind"], "ordinary")
        self.assertEqual(resolved["basis"], "operator_resolved")
        self.assertTrue(resolved["resolved_by_operator"])
        self.assertEqual(
            self.core.list_reply_associations(self.campaign["id"], status="associated"),
            [self.core.get_reply_association(ambiguous["id"])])

    def test_operator_can_dismiss_an_ambiguous_reply(self):
        self.ready_preparation()
        self.observe(inbound_message())
        ambiguous = self.core.list_reply_associations(status="ambiguous")[0]

        dismissed = self.core.resolve_reply_association(ambiguous["id"], dismiss=True)

        self.assertEqual(dismissed["status"], "dismissed")
        self.assertTrue(dismissed["resolved_by_operator"])
        self.assertEqual(self.core.list_reply_associations(
            self.campaign["id"], status="associated"), [])

    def test_resolution_rejects_a_task_outside_the_recorded_candidates(self):
        self.ready_preparation()
        self.observe(inbound_message())
        ambiguous = self.core.list_reply_associations(status="ambiguous")[0]
        with self.assertRaises(SmartMailError):
            self.core.resolve_reply_association(ambiguous["id"], "not-a-real-task")
        self.assertEqual(
            self.core.get_reply_association(ambiguous["id"])["status"], "ambiguous")


class ReplyPersistenceTests(ReplyAssociationTestCase):
    def test_associations_and_review_items_survive_restart(self):
        preparation = self.send_initial()
        refreshed = self.observe(inbound_message())
        association_id = self.core.list_reply_associations(self.campaign["id"])[0]["id"]

        self.core.__exit__(None, None, None)
        with SmartMail(self.home) as restarted:
            associations = restarted.list_reply_associations(self.campaign["id"])
            self.assertEqual(len(associations), 1)
            self.assertEqual(associations[0]["id"], association_id)
            self.assertEqual(associations[0]["task_id"], preparation["task_id"])
            self.assertEqual(
                restarted.get_reconciliation(refreshed["reconciliation"]["id"])
                ["summary"]["associated_replies"], 1)


class ReplyTerminalTests(unittest.TestCase):
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
        self.run_cli("execution", "run", confirmed[0]["id"], adapter=outcomes)
        return campaign, student

    def test_reply_review_and_resolution_through_the_terminal_boundary(self):
        campaign, student = self.build_sent_store()

        # A second Campaign prepares (but never sends) another Task to the same
        # Supervisor, so a subject-less reply cannot pick a Task deterministically.
        second_campaign = json.loads(
            self.run_cli("campaign", "create", "2028 outreach").stdout)
        members = [
            ("master.xlsx", master(self.directory / "master-2.xlsx", DEFAULT_ROWS)),
            (DRAFT_NAME, document(self.directory / "draft-2.docx",
                                  draft_paragraphs("alex@example.edu",
                                                   "Dear Dr Green,", [DECLARATION]))),
        ]
        second_bundle = bundle(self.directory / "bundle-2.zip", members)
        second_import = json.loads(self.run_cli(
            "import", str(second_bundle),
            "--campaign", second_campaign["id"], "--student", student["id"]).stdout)
        second_preparation = json.loads(self.run_cli(
            "prepare", "--import", second_import["id"]).stdout)["preparation_ids"][0]
        self.run_cli("preparation", "set-subject", second_preparation, "A different subject")

        observation = self.directory / "observation.json"
        observation.write_text(json.dumps({"observations": [
            inbound_refresh([inbound_message(subject=f"Out of Office Auto: {SUBJECT}")])]}),
            encoding="utf-8")
        refreshed = self.run_cli(
            "mailbox", "refresh", "--student", student["id"], adapter=observation)
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)

        listed = json.loads(self.run_cli(
            "reply", "list", "--campaign", campaign["id"]).stdout)
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["reply_kind"], "automatic")
        shown = json.loads(self.run_cli("reply", "show", listed[0]["id"]).stdout)
        self.assertEqual(shown, listed[0])

        # A second, ambiguous arrival is resolved to the Task from the shell.
        observation.write_text(json.dumps({"observations": [
            inbound_refresh([inbound_message(
                subject="Re: something else", reference="reply-9")],
                observed_at="2026-09-15T08:00:00+00:00")]}), encoding="utf-8")
        self.run_cli("mailbox", "refresh", "--student", student["id"], adapter=observation)
        ambiguous = json.loads(self.run_cli(
            "reply", "list", "--campaign", campaign["id"], "--status", "ambiguous").stdout)
        self.assertEqual(len(ambiguous), 1)
        resolved = self.run_cli(
            "reply", "resolve", ambiguous[0]["id"], "--task", ambiguous[0]["candidate_task_ids"][0])
        self.assertEqual(resolved.returncode, 0, resolved.stderr)
        self.assertEqual(json.loads(resolved.stdout)["reply_kind"], "ordinary")


if __name__ == "__main__":
    unittest.main()
