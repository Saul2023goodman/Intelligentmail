"""Ticket 11: operational reporting with filters, message states and drill-down."""

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from smartmail import SmartMail
from smartmail.mailbox import ControlledMailbox
from tests.test_execution import (
    DECLARATION, DRAFT_NAME, ROOT, SUBJECT, ExecutionTestCase,
    bundle, document, draft_paragraphs, master,
)
from tests.test_replies import inbound_refresh
from tests.test_followups import BODY_TEMPLATE, SUBJECT_TEMPLATE

UTC = timezone.utc
SEND_AT = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)


def outbound_message(counterpart, subject=SUBJECT, reference="scheduled-1",
                     status="scheduled", observed_time="2026-09-13T09:00:00+00:00"):
    return {
        "direction": "outbound", "folder": "sent", "platform_reference": reference,
        "counterpart": counterpart, "subject": subject,
        "observed_time": observed_time, "status": status, "ambiguity": "",
        "evidence": {"native_schedule_reference": reference},
    }


class ReportingTestCase(ExecutionTestCase):
    def add_task(self, label, address):
        student = self.core.create_student(label, f"{label.split()[0].lower()}@163.com")
        members = [
            ("master.xlsx", master(
                self.directory / f"master-{label.split()[0].lower()}.xlsx",
                [["Example University", f"Dr {label}", address, ""]])),
            (f"Example University_Dr {label}.docx", document(
                self.directory / f"draft-{label.split()[0].lower()}.docx",
                draft_paragraphs(address, f"Dear Dr {label},", [DECLARATION]))),
        ]
        path = bundle(self.directory / f"bundle-{label.split()[0].lower()}.zip", members)
        imported = self.core.import_master(self.campaign["id"], student["id"], path)
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        self.core.set_subject(preparation_id, SUBJECT)
        return student, self.core.get_preparation(preparation_id)

    def send(self, preparation, outcome="sent"):
        confirmation = self.core.confirm(preparation["id"], confirmed_at=SEND_AT)
        self.core.mailbox = ControlledMailbox([outcome])
        return self.core.run_execution([confirmation["id"]])

    def observe_outbound(self, preparation, *messages):
        task = self.core.get_task(preparation["task_id"])
        mailbox = ControlledMailbox(observations=[inbound_refresh(
            list(messages), mailbox=task["mailbox"]["address"])])
        self.core.mailbox = mailbox
        return self.core.refresh_mailbox(task["student"]["id"])

    def summary(self, **filters):
        return self.core.operations_report(self.campaign["id"], **filters)

    def task_ids(self, report):
        return [row["task_id"] for row in report["tasks"]]


class ReportSummaryTests(ReportingTestCase):
    def test_counts_and_filters_over_student_supervisor_institution_and_mailbox(self):
        student_a, planned = self.add_task("Alex Green", "alex@example.edu")
        student_b, sent = self.add_task("Blair Blue", "blair@example.edu")
        self.send(sent)

        report = self.summary()
        self.assertEqual(report["counts"]["tasks"], 2)
        self.assertEqual(report["counts"]["message_status"]["locally_planned"], 1)
        self.assertEqual(report["counts"]["message_status"]["sent"], 1)
        self.assertEqual(
            {row["message_status"] for row in report["tasks"]},
            {"locally_planned", "sent"})

        only_planned = self.summary(message_status="locally_planned")
        self.assertEqual(self.task_ids(only_planned), [planned["task_id"]])
        only_sent = self.summary(message_status="sent")
        self.assertEqual(self.task_ids(only_sent), [sent["task_id"]])

        by_student = self.summary(student_id=student_a["id"])
        self.assertEqual(self.task_ids(by_student), [planned["task_id"]])
        planned_task = self.core.get_task(planned["task_id"])
        by_supervisor = self.summary(supervisor_id=planned_task["supervisor"]["id"])
        self.assertEqual(self.task_ids(by_supervisor), [planned["task_id"]])
        by_institution = self.summary(
            institution_id=planned_task["institution"]["id"])
        self.assertEqual(len(by_institution["tasks"]), 2)
        by_mailbox = self.summary(mailbox=planned_task["mailbox"]["address"])
        self.assertEqual(self.task_ids(by_mailbox), [planned["task_id"]])

    def test_message_states_cover_scheduled_sent_failure_and_unknown(self):
        _, scheduled_prep = self.add_task("Carol Cyan", "carol@example.edu")
        self.observe_outbound(
            scheduled_prep, outbound_message("carol@example.edu", reference="native-1"))
        scheduled_report = self.summary(message_status="externally_scheduled")
        self.assertEqual(self.task_ids(scheduled_report), [scheduled_prep["task_id"]])
        scheduled_row = scheduled_report["tasks"][0]
        self.assertEqual(scheduled_row["message_status"], "externally_scheduled")

        # Failure and unknown outcomes each get their own paused Campaign.
        for outcome, state in (("failed", "observed_failure"),
                               ("unknown", "unknown_outcome")):
            with SmartMail(self.directory / f"state-{outcome}",
                           mailbox=ControlledMailbox([outcome])) as other:
                campaign = other.create_campaign(f"campaign-{outcome}")
                student = other.create_student(f"Dale {outcome}", f"dale-{outcome}@163.com")
                members = [
                    ("master.xlsx", master(
                        self.directory / f"master-{outcome}.xlsx",
                        [["Example University", f"Dr Dale {outcome}",
                          f"dale-{outcome}@example.edu", ""]])),
                    (f"Example University_Dr Dale {outcome}.docx", document(
                        self.directory / f"draft-{outcome}.docx",
                        draft_paragraphs(f"dale-{outcome}@example.edu", "Dear Dr Dale,",
                                         [DECLARATION]))),
                ]
                imported = other.import_master(
                    campaign["id"], student["id"],
                    bundle(self.directory / f"bundle-{outcome}.zip", members))
                preparation_id = other.prepare_from_documents(imported["id"])[
                    "preparation_ids"][0]
                other.set_subject(preparation_id, SUBJECT)
                confirmation = other.confirm(preparation_id, confirmed_at=SEND_AT)
                other.run_execution([confirmation["id"]])
                report = other.operations_report(campaign["id"])
                self.assertEqual(report["counts"]["message_status"][state], 1)
                self.assertEqual(report["flow"]["state"], "paused")

    def test_a_failed_follow_up_after_a_sent_initial_is_not_reported_as_sent(self):
        _, preparation = self.add_task("Jade Juniper", "jade@example.edu")
        self.send(preparation)
        self.core.configure_follow_up_rule(
            self.campaign["id"], delay_days=3, maximum_count=2,
            subject_template=SUBJECT_TEMPLATE, body_template=BODY_TEMPLATE)
        self.at(SEND_AT + timedelta(days=4))
        action = self.core.prepare_follow_ups(self.campaign["id"])[0]
        confirmation = self.core.confirm(action["preparation_id"])
        self.core.mailbox = ControlledMailbox(["failed"])
        self.core.run_execution([confirmation["id"]])

        report = self.summary()
        self.assertEqual(report["counts"]["message_status"]["observed_failure"], 1)
        self.assertEqual(report["counts"]["message_status"]["sent"], 0)
        detail = self.core.report_task(preparation["task_id"])
        self.assertEqual(detail["message_status"], "observed_failure")
        self.assertEqual(
            [attempt["state"] for attempt in detail["execution_attempts"]],
            ["sent", "failed"])

    def test_duplicate_status_filter_keeps_coverage_honest(self):
        _, preparation = self.add_task("Erin Ember", "erin@example.edu")
        check = self.core.check_duplicate(preparation["id"])
        self.assertEqual(check["finding"], "no_duplicate_found")

        found = self.summary(duplicate_status="no_duplicate_found")
        self.assertEqual(len(found["tasks"]), 1)
        self.assertEqual(found["tasks"][0]["duplicate_status"], "no_duplicate_found")
        unchecked = self.summary(duplicate_status="unchecked")
        self.assertEqual(unchecked["tasks"], [])
        row = found["tasks"][0]
        self.assertTrue(row["duplicate_coverage"]["limitations"])

    def test_exception_filters_distinguish_any_from_blocking(self):
        student = self.core.create_student("Fiona Forest", "fiona@163.com")
        members = [
            ("master.xlsx", master(self.directory / "master-fiona.xlsx", [
                ["Example University", "Dr Finn Gray", "finn@example.edu", ""],
                ["Example University", "Dr F. Gray", "finn@example.edu", ""],
            ])),
            ("Example University_Dr Finn Gray.docx", document(
                self.directory / "draft-fiona.docx",
                draft_paragraphs("finn@example.edu", "Dear Dr Gray,", [DECLARATION]))),
        ]
        imported = self.core.import_master(
            self.campaign["id"], student["id"],
            bundle(self.directory / "bundle-fiona.zip", members))
        self.assertTrue(imported["task_ids"])

        blocking = self.summary(exceptions="blocking")
        self.assertEqual(len(blocking["tasks"]), 2)
        self.assertTrue(all(row["exceptions"]["blocking"] for row in blocking["tasks"]))
        self.assertEqual(len(self.summary(exceptions="any")["tasks"]), 2)
        self.assertEqual(self.summary(exceptions="none")["tasks"], [])

    def test_follow_up_filter_reflects_eligibility_state(self):
        _, preparation = self.add_task("Gale Gold", "gale@example.edu")
        self.send(preparation)
        self.core.configure_follow_up_rule(
            self.campaign["id"], delay_days=3, maximum_count=2,
            subject_template=SUBJECT_TEMPLATE, body_template=BODY_TEMPLATE)
        self.at(SEND_AT + timedelta(days=2))
        self.assertEqual(self.summary(follow_up="due")["tasks"], [])
        self.assertEqual(
            len(self.summary(follow_up="waiting")["tasks"]), 1)
        self.at(SEND_AT + timedelta(days=4))
        due_report = self.summary(follow_up="due")
        self.assertEqual(len(due_report["tasks"]), 1)
        self.assertEqual(due_report["tasks"][0]["follow_up"], "due")


class ReportDrillDownTests(ReportingTestCase):
    def test_task_drill_down_collects_preparation_evidence_and_execution_history(self):
        student, preparation = self.add_task("Hayes Hill", "hayes@example.edu")
        self.send(preparation)
        self.core.check_duplicate(preparation["id"])
        task = self.core.get_task(preparation["task_id"])
        self.core.mailbox = ControlledMailbox(observations=[inbound_refresh([
            {"direction": "inbound", "folder": "inbox", "platform_reference": "reply-1",
             "counterpart": "hayes@example.edu",
             "subject": f"Out of Office: Re: {SUBJECT}",
             "observed_time": "2026-09-15T08:00:00+00:00", "status": "received",
             "ambiguity": "", "evidence": {}}], mailbox=task["mailbox"]["address"])])
        self.core.refresh_mailbox(student["id"])
        self.at(SEND_AT + timedelta(days=4))
        self.core.configure_follow_up_rule(
            self.campaign["id"], delay_days=3, maximum_count=2,
            subject_template=SUBJECT_TEMPLATE, body_template=BODY_TEMPLATE)
        action = self.core.prepare_follow_ups(self.campaign["id"])[0]

        detail = self.core.report_task(preparation["task_id"])

        self.assertEqual(detail["task"]["id"], preparation["task_id"])
        self.assertEqual(detail["message_status"], "sent")
        preparation_ids = [p["id"] for p in detail["preparations"]]
        self.assertIn(preparation["id"], preparation_ids)
        self.assertIn(action["preparation_id"], preparation_ids)
        self.assertEqual(
            {p["action_kind"] for p in detail["preparations"]}, {"initial", "follow_up"})
        self.assertTrue(detail["sources"])
        self.assertEqual(detail["sources"][0]["name"], "master.xlsx")
        self.assertEqual(len(detail["sent_records"]), 1)
        self.assertEqual(len(detail["execution_attempts"]), 1)
        self.assertEqual(detail["execution_attempts"][0]["state"], "sent")
        checks = detail["duplicate_checks"]
        self.assertEqual(checks[0]["finding"], "no_duplicate_found")
        self.assertIn("limitations", checks[0]["evidence_coverage"])
        self.assertEqual(len(detail["reply_associations"]), 1)
        self.assertEqual(detail["reply_associations"][0]["reply_kind"], "automatic")
        self.assertEqual(detail["follow_up"]["status"]["state"], "follow_up_open")
        self.assertEqual([a["id"] for a in detail["follow_up"]["actions"]], [action["id"]])


class ReportPersistenceTests(ReportingTestCase):
    def test_report_is_available_while_paused_and_reproduces_after_restart(self):
        _, preparation = self.add_task("Indigo Iris", "indigo@example.edu")
        self.send(preparation)
        self.core.configure_follow_up_rule(
            self.campaign["id"], delay_days=3, maximum_count=2,
            subject_template=SUBJECT_TEMPLATE, body_template=BODY_TEMPLATE)
        self.at(SEND_AT + timedelta(days=4))
        action = self.core.prepare_follow_ups(self.campaign["id"])[0]
        confirmation = self.core.confirm(action["preparation_id"])
        reply_at = SEND_AT + timedelta(days=5)
        self.at(reply_at)
        task = self.core.get_task(preparation["task_id"])
        self.core.mailbox = ControlledMailbox(observations=[inbound_refresh([
            {"direction": "inbound", "folder": "inbox", "platform_reference": "reply-2",
             "counterpart": "indigo@example.edu", "subject": f"Re: {SUBJECT}",
             "observed_time": reply_at.isoformat(), "status": "received",
             "ambiguity": "", "evidence": {}}],
            mailbox=task["mailbox"]["address"], observed_at=reply_at.isoformat())])
        self.core.refresh_mailbox(task["student"]["id"])
        paused_result = self.core.run_execution([confirmation["id"]])
        self.assertTrue(paused_result["paused"])

        # Reporting never requires an unpaused flow.
        report = self.summary()
        self.assertEqual(report["flow"]["state"], "paused")
        self.assertEqual(report["flow"]["reason"], "new_associated_reply")
        self.assertEqual(len(report["tasks"]), 1)

        self.core.__exit__(None, None, None)
        with SmartMail(self.directory / "state", mailbox=ControlledMailbox(),
                       clock=lambda: reply_at) as restarted:
            again = restarted.operations_report(self.campaign["id"])
            self.assertEqual(again["tasks"], report["tasks"])
            self.assertEqual(again["counts"], report["counts"])
            self.assertEqual(again["flow"], report["flow"])
            detail = restarted.report_task(preparation["task_id"])
            self.assertEqual(detail["follow_up"]["actions"][0]["status"], "prepared")


class ReportTerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state-terminal"

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "smartmail", "--home", str(self.home), *arguments],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def test_report_show_and_task_drill_down_through_the_shell(self):
        with SmartMail(self.home, mailbox=ControlledMailbox(),
                       clock=lambda: SEND_AT) as core:
            campaign = core.create_campaign("2027 outreach")
            student = core.create_student("Test Student", "student@163.com")
            members = [
                ("master.xlsx", master(
                    self.directory / "master.xlsx",
                    [["Example University", "Dr Alex Green", "alex@example.edu", ""]])),
                (DRAFT_NAME, document(
                    self.directory / "draft.docx",
                    draft_paragraphs("alex@example.edu", "Dear Dr Green,", [DECLARATION]))),
            ]
            imported = core.import_master(
                campaign["id"], student["id"],
                bundle(self.directory / "bundle.zip", members))
            preparation_id = core.prepare_from_documents(imported["id"])["preparation_ids"][0]
            core.set_subject(preparation_id, SUBJECT)
            confirmation = core.confirm(preparation_id)
            core.run_execution([confirmation["id"]])
            task_id = core.get_preparation(preparation_id)["task_id"]
            campaign_id = campaign["id"]

        report = json.loads(self.run_cli(
            "report", "show", "--campaign", campaign_id,
            "--message-status", "sent").stdout)
        self.assertEqual([row["task_id"] for row in report["tasks"]], [task_id])
        self.assertEqual(report["counts"]["message_status"]["sent"], 1)

        detail = json.loads(self.run_cli("report", "task", task_id).stdout)
        self.assertEqual(detail["task"]["id"], task_id)
        self.assertEqual(detail["message_status"], "sent")
        self.assertEqual(len(detail["execution_attempts"]), 1)


if __name__ == "__main__":
    unittest.main()
