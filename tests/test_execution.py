"""Controlled execution: confirmed Preparations only, evidence-based Sent Records, paused flows."""

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import Workbook

from smartmail import SmartMail, SmartMailError
from smartmail.mailbox import ControlledMailbox

ROOT = Path(__file__).resolve().parent.parent
DRAFT_NAME = "Example University_Dr Alex Green.docx"
DEFAULT_ROWS = [["Example University", "Dr Alex Green", "alex@example.edu", ""]]
DECLARATION = "I have attached my CV and would welcome the opportunity to discuss my background."
SUBJECT = "PhD supervision enquiry"


def master(path, rows, headers=None):
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(headers or ["大学", "导师", "邮箱📮", "URL"])
    for row in rows:
        sheet.append(row)
    workbook.save(path)
    workbook.close()
    return path


def draft_paragraphs(recipient, salutation, body, note=None):
    lines = [f"Email: {recipient}", "", "", "", salutation, ""]
    for paragraph in body:
        lines.extend([paragraph, ""])
    lines += ["Yours sincerely,", "Sipei Yao"]
    if note is not None:
        lines += ["", "", "", note]
    return lines


def document(path, paragraphs):
    namespace = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{escape(text)}</w:t></w:r></w:p>' for text in paragraphs
    )
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<w:document xmlns:w="{namespace}"><w:body>{body}</w:body></w:document>'
    )
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return path


def bundle(path, members):
    with zipfile.ZipFile(path, "w") as archive:
        for name, item in members:
            archive.write(item, name)
    return path


class ExecutionTestCase(unittest.TestCase):
    rows = DEFAULT_ROWS

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state"
        self.mailbox = ControlledMailbox()
        self.core = SmartMail(self.home, mailbox=self.mailbox)
        self.addCleanup(self.core.__exit__)
        self.campaign = self.core.create_campaign("2027 outreach")
        self.student = self.core.create_student("Test Student", "student@163.com")

    def script(self, *outcomes):
        self.mailbox = ControlledMailbox(list(outcomes))
        self.core.mailbox = self.mailbox
        return self.mailbox

    def import_bundle(self, documents, master_rows=None, extra=()):
        rows = master_rows if master_rows is not None else self.rows
        master_path = master(self.directory / "master.xlsx", rows)
        members = [("master.xlsx", master_path)]
        for index, (name, paragraphs) in enumerate(documents):
            members.append((name, document(self.directory / f"draft-{index}.docx", paragraphs)))
        for name, item in extra:
            members.append((name, item))
        source = bundle(self.directory / "bundle.zip", members)
        return self.core.import_master(self.campaign["id"], self.student["id"], source)

    def cv(self, text="Test Student"):
        content = [text, "E-mail: student@163.com"]
        path = document(self.directory / "cv.docx", content)
        return ("Test Student - CV.docx", path), path.read_bytes()

    def ready_preparation(self, body=(DECLARATION,), attach=True, subject=SUBJECT):
        (cv_name, cv_path), cv_bytes = self.cv()
        imported = self.import_bundle(
            [(DRAFT_NAME, draft_paragraphs("alex@example.edu", "Dear Dr Green,", list(body)))],
            extra=[(cv_name, cv_path)])
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        if subject is not None:
            self.core.set_subject(preparation_id, subject)
        if attach:
            slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
            self.core.confirm_attachment(preparation_id, slot["id"])
        return self.core.get_preparation(preparation_id), cv_bytes

    def two_ready_preparations(self):
        rows = [["Example University", "Dr Alex Green", "alex@example.edu", ""],
                ["Example University", "Dr Blair Blue", "blair@example.edu", ""]]
        (cv_name, cv_path), _ = self.cv()
        imported = self.import_bundle([
            (DRAFT_NAME, draft_paragraphs("alex@example.edu", "Dear Dr Green,", [DECLARATION])),
            ("Example University_Dr Blair Blue.docx",
             draft_paragraphs("blair@example.edu", "Dear Dr Blue,", [DECLARATION])),
        ], master_rows=rows, extra=[(cv_name, cv_path)])
        ids = self.core.prepare_from_documents(imported["id"])["preparation_ids"]
        for preparation_id in ids:
            self.core.set_subject(preparation_id, SUBJECT)
        return ids


class NoUnconfirmedRequestTests(ExecutionTestCase):
    def test_local_preparation_and_confirmation_make_no_external_request(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])

        self.assertEqual(self.mailbox.requests, [])
        self.assertEqual(self.core.list_execution_attempts(self.campaign["id"]), [])
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "idle")
        self.assertEqual(self.core.get_confirmation(confirmation["id"])["status"], "active")


class SuccessfulExecutionTests(ExecutionTestCase):
    def test_a_confirmed_ready_preparation_sends_and_freezes_an_immutable_sent_record(self):
        preparation, cv_bytes = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])

        result = self.core.run_execution([confirmation["id"]])

        self.assertEqual(len(result["attempts"]), 1)
        attempt = result["attempts"][0]
        self.assertEqual(attempt["state"], "sent")
        self.assertEqual(attempt["preparation_id"], preparation["id"])
        self.assertFalse(result["paused"])
        self.assertEqual(result["flow"]["state"], "idle")

        self.assertEqual(len(self.mailbox.requests), 1)
        request = self.mailbox.requests[0]
        self.assertEqual(request["sender"], "student@163.com")
        self.assertEqual(request["recipient"], "alex@example.edu")
        self.assertEqual(request["subject"], SUBJECT)
        self.assertIn("Dear Dr Green,", request["body"])
        self.assertEqual(request["attachments"][0]["name"], "Test Student - CV.docx")
        self.assertEqual(request["attachments"][0]["sha256"],
                         attempt["request"]["attachments"][0]["sha256"])

        self.assertEqual(self.core.get_confirmation(confirmation["id"])["status"], "consumed")
        self.assertTrue(self.core.review_confirmation(preparation["id"])["already_sent"])

        sent = self.core.get_sent_record(attempt["sent_record_id"])
        self.assertEqual(sent["sender"], "student@163.com")
        self.assertEqual(sent["recipient"], "alex@example.edu")
        self.assertEqual(sent["subject"], SUBJECT)
        self.assertEqual(sent["evidence"], {"outcome": "sent", "reference": "controlled-sent", "detail": ""})
        self.assertEqual(self.core.read_sent_attachment(sent["attachments"][0]["id"]), cv_bytes)
        self.assertEqual([r["id"] for r in self.core.list_sent_records(self.campaign["id"])],
                         [sent["id"]])

    def test_the_sent_record_stays_frozen_after_later_local_edits(self):
        preparation, cv_bytes = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        attempt = self.core.run_execution([confirmation["id"]])["attempts"][0]
        sent = self.core.get_sent_record(attempt["sent_record_id"])

        self.core.set_subject(preparation["id"], "Locally changed afterwards")
        replacement = self.directory / "replacement.pdf"
        replacement.write_bytes(b"different bytes")
        slot = self.core.get_preparation(preparation["id"])["attachment_slots"][0]
        self.core.set_attachment(preparation["id"], slot["id"], path=replacement)

        frozen = self.core.get_sent_record(sent["id"])
        self.assertEqual(frozen["subject"], SUBJECT)
        self.assertEqual(self.core.read_sent_attachment(sent["attachments"][0]["id"]), cv_bytes)

    def test_an_already_executed_action_cannot_execute_again(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        self.core.run_execution([confirmation["id"]])

        with self.assertRaises(SmartMailError):
            self.core.run_execution([confirmation["id"]])
        with self.assertRaises(SmartMailError):
            self.core.confirm(preparation["id"])
        self.assertEqual(len(self.mailbox.requests), 1)


class EligibilityTests(ExecutionTestCase):
    def test_execution_refuses_when_content_changed_after_confirmation(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        self.core.set_subject(preparation["id"], "Changed after confirmation")

        with self.assertRaises(SmartMailError):
            self.core.run_execution([confirmation["id"]])
        self.assertEqual(self.mailbox.requests, [])

    def test_execution_refuses_when_a_new_blocker_appears(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        self.core.set_recipient(preparation["id"], "someone-else@example.edu")

        with self.assertRaises(SmartMailError):
            self.core.run_execution([confirmation["id"]])
        self.assertEqual(self.mailbox.requests, [])

    def test_execution_requires_an_enabled_controlled_capability(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        with SmartMail(self.home) as disabled:
            with self.assertRaises(SmartMailError):
                disabled.run_execution([confirmation["id"]])
        self.assertEqual(self.mailbox.requests, [])

    def test_execution_of_an_unknown_confirmation_is_reported(self):
        with self.assertRaises(SmartMailError):
            self.core.run_execution(["unknown"])
        self.assertEqual(self.mailbox.requests, [])


class PausedFlowTests(ExecutionTestCase):
    def test_an_observed_failure_pauses_the_flow_and_records_evidence(self):
        self.script("failed")
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])

        result = self.core.run_execution([confirmation["id"]])

        self.assertTrue(result["paused"])
        self.assertEqual(result["flow"]["state"], "paused")
        self.assertEqual(result["flow"]["reason"], "execution_failed")
        self.assertEqual(result["attempts"][0]["state"], "failed")
        self.assertEqual(result["attempts"][0]["evidence"]["outcome"], "failed")
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])
        self.assertEqual(self.core.get_confirmation(confirmation["id"])["status"], "active")

        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "paused")
        with self.assertRaises(SmartMailError):
            self.core.run_execution([confirmation["id"]])
        self.assertEqual([p["id"] for p in self.core.list_preparations(self.campaign["id"])],
                         [preparation["id"]])
        self.assertTrue(self.core.review_confirmation(preparation["id"])["ready"])

    def test_a_batch_stops_after_a_blocking_failure(self):
        self.script("failed", "sent")
        ids = self.two_ready_preparations()
        confirmations = self.core.confirm_preparations(ids)

        result = self.core.run_execution([c["id"] for c in confirmations])

        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(result["attempts"][0]["preparation_id"], ids[0])
        self.assertEqual(result["attempts"][0]["state"], "failed")
        self.assertEqual(len(self.mailbox.requests), 1)
        self.assertEqual(self.core.get_confirmation(confirmations[1]["id"])["status"], "active")
        self.assertEqual(self.core.list_execution_attempts(self.campaign["id"]),
                         [result["attempts"][0]])

    def test_unknown_outcome_pauses_without_claiming_success(self):
        self.script({"outcome": "unknown", "detail": "connection lost"})
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])

        result = self.core.run_execution([confirmation["id"]])

        self.assertTrue(result["paused"])
        self.assertEqual(result["flow"]["reason"], "unknown_outcome")
        self.assertEqual(result["flow"]["detail"], "connection lost")
        attempt = result["attempts"][0]
        self.assertEqual(attempt["state"], "unknown")
        self.assertIsNone(attempt["sent_record_id"])
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])
        self.assertEqual(self.core.get_confirmation(confirmation["id"])["status"], "active")


class StopAndRewriteTests(ExecutionTestCase):
    def revised_source(self, body=(DECLARATION,)):
        imported = self.import_bundle(
            [(DRAFT_NAME, draft_paragraphs("alex@example.edu", "Dear Dr Green,", list(body)))])
        return next(s for s in self.core.get_import(imported["id"])["sources"]
                    if s["name"] == DRAFT_NAME)

    def test_stop_releases_an_unknown_attempt_and_clears_the_pause(self):
        self.script({"outcome": "unknown", "detail": "connection lost"})
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        attempt = self.core.run_execution([confirmation["id"]])["attempts"][0]

        stopped = self.core.stop_execution_attempt(attempt["id"], detail="operator stopped before retry")

        self.assertEqual(stopped["state"], "stopped")
        self.assertTrue(stopped["evidence"]["stopped"])
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "idle")
        self.assertEqual(self.core.get_execution_attempt(attempt["id"])["state"], "stopped")

    def test_rewrite_is_refused_while_an_attempt_is_unresolved_and_allowed_after_stopping(self):
        self.script({"outcome": "unknown"})
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        attempt = self.core.run_execution([confirmation["id"]])["attempts"][0]

        with self.assertRaises(SmartMailError):
            self.core.rewrite(preparation["id"],
                              source_id=self.revised_source(["Second version."])["id"])
        self.assertEqual(self.core.get_preparation(preparation["id"])["status"], "active")

        self.core.stop_execution_attempt(attempt["id"])
        replaced = self.core.rewrite(preparation["id"],
                                     source_id=self.revised_source(["Second version."])["id"])

        self.assertNotEqual(replaced["id"], preparation["id"])

    def test_rewrite_invalidates_the_replaced_preparations_confirmation(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])

        replaced = self.core.rewrite(preparation["id"],
                                     source_id=self.revised_source(["Second version."])["id"])

        self.assertEqual(self.core.get_confirmation(confirmation["id"])["status"], "invalidated")
        self.assertEqual(self.core.get_confirmation(confirmation["id"])["invalidated_reason"], "rewrite")
        self.assertEqual(self.core.list_confirmations(self.campaign["id"]), [])
        self.assertIsNone(self.core.review_confirmation(replaced["id"])["confirmation_id"])

    def test_post_sent_communication_requires_a_new_linked_action(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        self.core.run_execution([confirmation["id"]])

        with self.assertRaises(SmartMailError):
            self.core.rewrite(preparation["id"],
                              source_id=self.revised_source(["Second version."])["id"])
        with self.assertRaises(SmartMailError):
            self.core.confirm(preparation["id"])

        review = self.core.review_confirmation(preparation["id"])
        self.assertTrue(review["already_sent"])
        self.assertIsNone(review["confirmation_id"])

    def test_stop_refuses_an_attempt_that_is_not_active_and_an_unknown_id(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        sent_attempt = self.core.run_execution([confirmation["id"]])["attempts"][0]

        with self.assertRaises(SmartMailError):
            self.core.stop_execution_attempt(sent_attempt["id"])
        with self.assertRaises(SmartMailError):
            self.core.stop_execution_attempt("unknown")


class PersistenceTests(ExecutionTestCase):
    def test_confirmations_attempts_and_sent_records_survive_restart(self):
        preparation, cv_bytes = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        attempt = self.core.run_execution([confirmation["id"]])["attempts"][0]

        with SmartMail(self.home, mailbox=ControlledMailbox()) as restarted:
            self.assertEqual(restarted.get_confirmation(confirmation["id"])["status"], "consumed")
            self.assertEqual(restarted.get_execution_attempt(attempt["id"])["state"], "sent")
            sent = restarted.get_sent_record(attempt["sent_record_id"])
            self.assertEqual(sent["subject"], SUBJECT)
            self.assertEqual(restarted.read_sent_attachment(sent["attachments"][0]["id"]), cv_bytes)
            self.assertTrue(restarted.review_confirmation(preparation["id"])["already_sent"])

    def test_a_paused_flow_survives_restart(self):
        self.script("failed")
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        self.core.run_execution([confirmation["id"]])

        with SmartMail(self.home, mailbox=ControlledMailbox()) as restarted:
            status = restarted.execution_status(self.campaign["id"])
            self.assertEqual(status["state"], "paused")
            self.assertEqual(status["reason"], "execution_failed")
            with self.assertRaises(SmartMailError):
                restarted.run_execution([confirmation["id"]])


class TerminalExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state-terminal"

    def run_cli(self, *arguments, adapter=None):
        prefix = [sys.executable, "-m", "smartmail", "--home", str(self.home)]
        if adapter is not None:
            prefix += ["--adapter", "controlled", "--adapter-script", str(adapter)]
        return subprocess.run(
            [*prefix, *arguments], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def script(self, *outcomes):
        path = self.directory / "outcomes.json"
        path.write_text(json.dumps({"outcomes": list(outcomes)}), encoding="utf-8")
        return path

    def build_store(self):
        campaign = json.loads(self.run_cli("campaign", "create", "2027 outreach").stdout)
        student = json.loads(self.run_cli(
            "student", "create", "Test Student", "--mailbox", "student@163.com").stdout)
        master_path = master(self.directory / "master.xlsx", DEFAULT_ROWS)
        docx = document(self.directory / "draft.docx",
                        draft_paragraphs("alex@example.edu", "Dear Dr Green,", [DECLARATION]))
        cv_path = document(self.directory / "cv.docx", ["Test Student", "E-mail: student@163.com"])
        source = bundle(self.directory / "bundle.zip", [
            ("master.xlsx", master_path), (DRAFT_NAME, docx), ("Test Student - CV.docx", cv_path)])
        imported = json.loads(self.run_cli(
            "import", str(source), "--campaign", campaign["id"], "--student", student["id"]).stdout)
        preparation_id = json.loads(
            self.run_cli("prepare", "--import", imported["id"]).stdout)["preparation_ids"][0]
        self.run_cli("preparation", "set-subject", preparation_id, SUBJECT)
        slot = json.loads(self.run_cli(
            "preparation", "show", preparation_id).stdout)["attachment_slots"][0]
        self.run_cli("preparation", "confirm", preparation_id, "--slot", slot["id"])
        return campaign, preparation_id

    def test_terminal_confirms_executes_and_reports_the_sent_record(self):
        campaign, preparation_id = self.build_store()
        review = json.loads(self.run_cli("confirmation", "review", preparation_id).stdout)
        self.assertEqual(review["subject"], SUBJECT)
        self.assertEqual(review["execution"], {"kind": "immediate"})
        self.assertEqual([a["name"] for a in review["attachments"]], ["Test Student - CV.docx"])

        confirmed = json.loads(self.run_cli("confirmation", "confirm", preparation_id).stdout)
        self.assertEqual([c["preparation_id"] for c in confirmed], [preparation_id])

        ran = self.run_cli("execution", "run", confirmed[0]["id"], adapter=self.script("sent"))
        self.assertEqual(ran.returncode, 0, ran.stderr)
        result = json.loads(ran.stdout)
        self.assertEqual(result["attempts"][0]["state"], "sent")
        sent_id = result["attempts"][0]["sent_record_id"]

        sent = json.loads(self.run_cli("sent", "show", sent_id).stdout)
        self.assertEqual(sent["subject"], SUBJECT)
        self.assertEqual(sent["attachments"][0]["name"], "Test Student - CV.docx")
        listed = json.loads(self.run_cli("sent", "list", "--campaign", campaign["id"]).stdout)
        self.assertEqual([record["id"] for record in listed], [sent_id])
        status = json.loads(self.run_cli("execution", "status", "--campaign", campaign["id"]).stdout)
        self.assertEqual(status["state"], "idle")

        again = self.run_cli("execution", "run", confirmed[0]["id"], adapter=self.script("sent"))
        self.assertEqual(again.returncode, 2)
        self.assertIn("error", json.loads(again.stderr))

    def test_terminal_unknown_outcome_pauses_and_stop_releases_it(self):
        campaign, preparation_id = self.build_store()
        confirmed = json.loads(self.run_cli("confirmation", "confirm", preparation_id).stdout)
        script = self.script({"outcome": "unknown", "detail": "connection lost"})

        ran = self.run_cli("execution", "run", confirmed[0]["id"], adapter=script)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        result = json.loads(ran.stdout)
        attempt_id = result["attempts"][0]["id"]
        self.assertTrue(result["paused"])

        status = json.loads(self.run_cli("execution", "status", "--campaign", campaign["id"]).stdout)
        self.assertEqual(status["state"], "paused")
        self.assertEqual(status["reason"], "unknown_outcome")
        self.assertEqual(self.run_cli(
            "execution", "run", confirmed[0]["id"], adapter=script).returncode, 2)

        stopped = json.loads(self.run_cli(
            "execution", "stop", attempt_id, "--detail", "operator stopped").stdout)
        self.assertEqual(stopped["state"], "stopped")
        self.assertEqual(json.loads(
            self.run_cli("execution", "status", "--campaign", campaign["id"]).stdout)["state"], "idle")

    def test_terminal_execution_is_disabled_without_a_verified_capability(self):
        campaign, preparation_id = self.build_store()
        confirmed = json.loads(self.run_cli("confirmation", "confirm", preparation_id).stdout)

        ran = self.run_cli("execution", "run", confirmed[0]["id"])

        self.assertEqual(ran.returncode, 2)
        self.assertIn("disabled", json.loads(ran.stderr)["error"])


if __name__ == "__main__":
    unittest.main()
