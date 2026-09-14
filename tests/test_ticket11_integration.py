"""Ticket 11 integrated scenario: intake to replies, linked follow-ups and reports.

One persistent store drives the whole closed loop through the public SmartMail
boundary with the controlled mailbox adapter and controlled time:

intake and attachment resolution -> Confirmation -> controlled sends ->
immutable Sent Records -> Ordinary and Automatic replies -> deterministic
Follow-up Due -> linked Follow-up Action with its own Confirmation ->
ambiguous review and resolution -> operational drill-down -> restart.
"""

import unittest
from datetime import datetime, timedelta, timezone

from smartmail import SmartMail, SmartMailError
from smartmail.mailbox import ControlledMailbox
from tests.test_execution import (
    DECLARATION, DEFAULT_ROWS, DRAFT_NAME, SUBJECT, ExecutionTestCase,
    bundle, document, draft_paragraphs, master,
)
from tests.test_replies import inbound_refresh
from tests.test_followups import BODY_TEMPLATE, SUBJECT_TEMPLATE

UTC = timezone.utc
SEND_AT = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)


class Ticket11IntegratedScenarioTests(ExecutionTestCase):
    MAILBOX = "student@163.com"

    def inbound(self, counterpart, subject, reference, observed_at, *, automatic=False):
        message = {
            "direction": "inbound", "folder": "inbox", "platform_reference": reference,
            "counterpart": counterpart, "subject": subject,
            "observed_time": observed_at, "status": "received", "ambiguity": "",
            "evidence": {} if not automatic else {"auto_submitted": "auto-replied"},
        }
        self.core.mailbox = ControlledMailbox(observations=[inbound_refresh(
            [message], mailbox=self.MAILBOX, observed_at=observed_at)])
        return self.core.refresh_mailbox(self.student["id"])

    def test_the_full_reply_and_follow_up_loop_is_reproducible_after_restart(self):
        self.at(SEND_AT)

        # --- Intake: two Tasks from one bundle, attachments resolved ------
        second_draft = "Example University_Dr Blair Blue.docx"
        members = [
            ("master.xlsx", master(self.directory / "master.xlsx", [
                ["Example University", "Dr Alex Green", "alex@example.edu", ""],
                ["Example University", "Dr Blair Blue", "blair@example.edu", ""],
            ])),
            (DRAFT_NAME, document(
                self.directory / "alex.docx",
                draft_paragraphs("alex@example.edu", "Dear Dr Green,", [DECLARATION]))),
            (second_draft, document(
                self.directory / "blair.docx",
                draft_paragraphs("blair@example.edu", "Dear Dr Blue,", [DECLARATION]))),
            ("Test Student - CV.docx", document(
                self.directory / "cv.docx",
                ["Test Student", "E-mail: student@163.com"])),
        ]
        imported = self.core.import_master(
            self.campaign["id"], self.student["id"],
            bundle(self.directory / "bundle.zip", members))
        preparation_ids = self.core.prepare_from_documents(imported["id"])["preparation_ids"]
        self.assertEqual(len(preparation_ids), 2)
        for preparation_id in preparation_ids:
            self.core.set_subject(preparation_id, SUBJECT)
            slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
            self.core.confirm_attachment(preparation_id, slot["id"])
        tasks = {self.core.get_preparation(pid)["recipient"]: pid
                 for pid in preparation_ids}
        alex_preparation = self.core.get_preparation(tasks["alex@example.edu"])
        blair_preparation = self.core.get_preparation(tasks["blair@example.edu"])

        # --- Confirmation and controlled sends ----------------------------
        confirmations = self.core.confirm_preparations(preparation_ids)
        self.core.mailbox = ControlledMailbox(["sent", "sent"])
        result = self.core.run_execution([c["id"] for c in confirmations])
        self.assertFalse(result["paused"])
        initial_records = self.core.list_sent_records(self.campaign["id"])
        self.assertEqual(len(initial_records), 2)
        self.assertTrue(all(record["action_kind"] == "initial" for record in initial_records))

        # --- Replies: Alex ordinary, Blair automatic ----------------------
        self.inbound("alex@example.edu", f"Re: {SUBJECT}", "reply-alex",
                     "2026-09-15T08:00:00+00:00")
        self.inbound("blair@example.edu", f"Re: {SUBJECT}", "reply-blair",
                     "2026-09-15T09:00:00+00:00", automatic=True)
        associations = self.core.list_reply_associations(self.campaign["id"])
        kinds = {a["observation"]["counterpart"]: a for a in associations}
        self.assertEqual(kinds["alex@example.edu"]["reply_kind"], "ordinary")
        self.assertEqual(kinds["blair@example.edu"]["reply_kind"], "automatic")
        self.assertIn("message_body_html",
                      kinds["alex@example.edu"]["evidence_coverage"]["excluded_fields"])

        # --- Eligibility diverges purely on reliable reply evidence -------
        self.core.configure_follow_up_rule(
            self.campaign["id"], delay_days=3, maximum_count=1,
            subject_template=SUBJECT_TEMPLATE, body_template=BODY_TEMPLATE)
        self.at(SEND_AT + timedelta(days=4))
        statuses = {view["task_id"]: view
                    for view in self.core.follow_up_status(self.campaign["id"])}
        self.assertEqual(statuses[alex_preparation["task_id"]]["state"],
                         "ordinary_reply_received")
        self.assertEqual(statuses[blair_preparation["task_id"]]["state"], "due")

        # Only Blair's linked Follow-up Action is prepared and confirmed.
        actions = self.core.prepare_follow_ups(self.campaign["id"])
        self.assertEqual(len(actions), 1)
        blair_action = actions[0]
        self.assertEqual(blair_action["task_id"], blair_preparation["task_id"])
        self.assertEqual(blair_action["status"], "prepared")
        follow_up_preparation = self.core.get_preparation(blair_action["preparation_id"])
        self.assertEqual(follow_up_preparation["action_kind"], "follow_up")
        self.assertEqual(
            self.core.check_duplicate(follow_up_preparation["id"])["finding"],
            "linked_follow_up")
        follow_up_confirmation = self.core.confirm(follow_up_preparation["id"])
        self.core.mailbox = ControlledMailbox(["sent"])
        follow_up_result = self.core.run_execution([follow_up_confirmation["id"]])
        self.assertFalse(follow_up_result["paused"])
        self.assertEqual(len(self.core.list_sent_records(self.campaign["id"])), 3)
        self.assertEqual(
            self.core.get_follow_up_action(blair_action["id"])["status"], "sent")
        self.assertEqual(
            next(v for v in self.core.follow_up_status(self.campaign["id"])
                 if v["task_id"] == blair_preparation["task_id"])["state"],
            "maximum_reached")

        # --- Ambiguous arrival across two Campaigns needs the operator ----
        second_campaign = self.core.create_campaign("2028 outreach")
        second_bundle = bundle(self.directory / "bundle-2028.zip", [
            ("master.xlsx", master(self.directory / "master-2028.xlsx", [
                ["Example University", "Dr Blair Blue", "blair@example.edu", ""]])),
            (second_draft, document(
                self.directory / "blair-2028.docx",
                draft_paragraphs("blair@example.edu", "Dear Dr Blue,", [DECLARATION]))),
        ])
        second_import = self.core.import_master(
            second_campaign["id"], self.student["id"], second_bundle)
        second_preparation_id = self.core.prepare_from_documents(
            second_import["id"])["preparation_ids"][0]
        self.core.set_subject(second_preparation_id, "A different topic")
        second_task_id = self.core.get_preparation(second_preparation_id)["task_id"]

        self.inbound("blair@example.edu", "Re: unrelated thread", "reply-ambiguous",
                     "2026-09-20T08:00:00+00:00")
        ambiguous = self.core.list_reply_associations(
            self.campaign["id"], status="ambiguous")
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(
            set(ambiguous[0]["candidate_task_ids"]),
            {blair_preparation["task_id"], second_task_id})
        with self.assertRaises(SmartMailError):
            self.core.resolve_reply_association(ambiguous[0]["id"], dismiss=False)
        resolved = self.core.resolve_reply_association(
            ambiguous[0]["id"], second_task_id)
        self.assertEqual(resolved["status"], "associated")
        self.assertEqual(resolved["reply_kind"], "ordinary")
        self.assertTrue(resolved["resolved_by_operator"])

        # --- Reporting summarizes and drills down while idle --------------
        report = self.core.operations_report(self.campaign["id"])
        self.assertEqual(report["counts"]["tasks"], 2)
        self.assertEqual(report["counts"]["message_status"]["sent"], 2)
        alex_only = self.core.operations_report(
            self.campaign["id"], follow_up="ordinary_reply_received")
        self.assertEqual([row["task_id"] for row in alex_only["tasks"]],
                         [alex_preparation["task_id"]])
        blair_detail = self.core.report_task(blair_preparation["task_id"])
        self.assertEqual(len(blair_detail["sent_records"]), 2)
        self.assertEqual(
            [record["action_kind"] for record in blair_detail["sent_records"]],
            ["initial", "follow_up"])
        self.assertEqual(
            blair_detail["sent_records"][-1]["follows_sent_record_id"],
            blair_detail["sent_records"][0]["id"])
        self.assertEqual(
            blair_detail["reply_associations"][0]["reply_kind"], "automatic")
        self.assertEqual(blair_detail["follow_up"]["status"]["state"],
                         "maximum_reached")
        alex_detail = self.core.report_task(alex_preparation["task_id"])
        self.assertEqual(
            alex_detail["reply_associations"][0]["reply_kind"], "ordinary")

        # --- Restart reproduces every persisted decision ------------------
        self.core.__exit__(None, None, None)
        restart_at = SEND_AT + timedelta(days=6)
        with SmartMail(self.directory / "state", mailbox=ControlledMailbox(),
                       clock=lambda: restart_at) as restarted:
            statuses_after = {v["task_id"]: v
                              for v in restarted.follow_up_status(self.campaign["id"])}
            self.assertEqual(statuses_after[alex_preparation["task_id"]]["state"],
                             "ordinary_reply_received")
            self.assertEqual(statuses_after[blair_preparation["task_id"]]["state"],
                             "maximum_reached")
            self.assertEqual(len(restarted.list_reply_associations(status="associated")), 3)
            after = restarted.operations_report(self.campaign["id"])
            self.assertEqual(after["counts"], report["counts"])
            self.assertEqual(
                [a["status"] for a in restarted.list_follow_up_actions(self.campaign["id"])],
                ["sent"])


if __name__ == "__main__":
    unittest.main()
