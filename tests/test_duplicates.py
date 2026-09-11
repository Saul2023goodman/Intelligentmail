"""Ticket 07: historical duplicate detection with recorded Evidence Coverage."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from smartmail import SmartMail, SmartMailError
from smartmail.mailbox import ControlledMailbox
from tests.test_execution import (
    DECLARATION, DEFAULT_ROWS, DRAFT_NAME, ROOT, SUBJECT, ExecutionTestCase,
    bundle, document, draft_paragraphs, master,
)

PROFILE = "https://example.edu/green"


def outbound_sent_observation(recipient, subject="Research", reference="prior-send-1"):
    """A persisted mailbox observation of an earlier outbound message."""
    return {
        "status": "complete",
        "mailbox_address": "student@163.com",
        "observed_at": "2026-09-11T07:30:00+00:00",
        "detail": "controlled prior-send history",
        "coverage": {"complete": False, "supported_scope_complete": True, "folders": [
            {"folder": "sent", "declared_total": 1, "ids_enumerated": 1,
             "enumeration_complete": True, "detail_complete": True, "complete": True}]},
        "messages": [{"direction": "outbound", "folder": "sent",
                      "platform_reference": reference, "counterpart": recipient,
                      "subject": subject, "observed_time": "2026年9月10日 10:00",
                      "status": "sent", "evidence": {"marker": "发送成功"}}],
    }


class DuplicateHistoryTestCase(ExecutionTestCase):
    def observe(self, observation):
        self.mailbox = ControlledMailbox(observations=[observation])
        self.core.mailbox = self.mailbox
        return self.core.refresh_mailbox(self.student["id"])

    def preparation_with_alternate_address(self):
        (cv_name, cv_path), _ = self.cv()
        imported = self.import_bundle(
            [(DRAFT_NAME, draft_paragraphs("alex@example.edu", "Dear Dr Green,", [DECLARATION]))],
            master_rows=[["Example University", "Dr Alex Green", "alex@example.edu", PROFILE],
                         ["Example University", "Dr Alex Green", "a.green@example.edu", PROFILE]],
            extra=[(cv_name, cv_path)])
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        self.core.set_subject(preparation_id, SUBJECT)
        slot = self.core.get_preparation(preparation_id)["attachment_slots"][0]
        self.core.confirm_attachment(preparation_id, slot["id"])
        return self.core.get_preparation(preparation_id)


class NoDuplicateFoundTests(ExecutionTestCase):
    def test_a_fresh_preparation_reports_no_duplicate_found_with_coverage(self):
        preparation, _ = self.ready_preparation()

        check = self.core.check_duplicate(preparation["id"])

        self.assertEqual(check["finding"], "no_duplicate_found")
        self.assertFalse(check["review_required"])
        self.assertEqual(check["preparation_id"], preparation["id"])
        self.assertEqual(check["task_id"], preparation["task_id"])
        self.assertEqual(check["matches"], [])

        sources = {source["source"]: source for source in check["evidence_coverage"]["sources"]}
        self.assertTrue(sources["sent_records"]["complete"])
        self.assertEqual(sources["sent_records"]["inspected"], 0)
        self.assertFalse(sources["mailbox_observations"]["complete"])
        self.assertFalse(check["evidence_coverage"]["complete"])

        persisted = self.core.get_duplicate_check(check["id"])
        self.assertEqual(persisted, check)


class RepeatExecutionTests(ExecutionTestCase):
    def test_an_already_executed_action_is_reported_as_repeat_execution(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        self.core.run_execution([confirmation["id"]])

        check = self.core.check_duplicate(preparation["id"])

        self.assertEqual(check["finding"], "repeat_execution")
        self.assertTrue(check["review_required"])
        self.assertEqual(check["matches"][0]["basis"], "same_action")
        self.assertEqual(check["matches"][0]["source"], "sent_record")
        with self.assertRaises(SmartMailError):
            self.core.run_execution([confirmation["id"]])
        self.assertEqual(len(self.mailbox.requests), 1)


class DuplicateSuspicionTests(DuplicateHistoryTestCase):
    def test_a_prior_send_to_a_known_supervisor_address_is_duplicate_suspicion(self):
        preparation, _ = self.ready_preparation()

        self.observe(outbound_sent_observation("alex@example.edu"))

        check = self.core.check_duplicate(preparation["id"])
        self.assertEqual(check["finding"], "duplicate_suspicion")
        self.assertTrue(check["review_required"])
        self.assertEqual(check["basis"], "known_supervisor_address")
        self.assertEqual(check["matches"][0]["source"], "mailbox_observation")
        self.assertEqual(check["matches"][0]["recipient"], "alex@example.edu")
        self.assertTrue(check["evidence_coverage"]["complete"])

    def test_a_prior_send_to_a_known_alternate_address_is_duplicate_suspicion(self):
        preparation = self.preparation_with_alternate_address()

        self.observe(outbound_sent_observation("a.green@example.edu"))

        check = self.core.check_duplicate(preparation["id"])
        self.assertEqual(check["finding"], "duplicate_suspicion")
        self.assertEqual(check["matches"][0]["recipient"], "a.green@example.edu")
        self.assertIn("a.green@example.edu",
                      check["evidence_coverage"]["supervisor_addresses"])

    def test_a_prior_send_to_an_unrelated_recipient_is_not_a_duplicate(self):
        preparation, _ = self.ready_preparation()

        self.observe(outbound_sent_observation("someone-else@example.edu"))

        check = self.core.check_duplicate(preparation["id"])
        self.assertEqual(check["finding"], "no_duplicate_found")
        self.assertFalse(check["review_required"])
        self.assertEqual(check["matches"], [])


class DistinctStudentTests(DuplicateHistoryTestCase):
    def _preparation_for(self, student_id):
        (cv_name, cv_path), _ = self.cv()
        members = [
            ("master.xlsx", master(self.directory / f"master-{student_id}.xlsx",
                                   [["Example University", "Dr Alex Green",
                                     "alex@example.edu", ""]])),
            (DRAFT_NAME, document(self.directory / f"draft-{student_id}.docx",
                                  draft_paragraphs("alex@example.edu",
                                                   "Dear Dr Green,", [DECLARATION]))),
            (cv_name, cv_path),
        ]
        imported = self.core.import_master(
            self.campaign["id"], student_id,
            bundle(self.directory / f"bundle-{student_id}.zip", members))
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        self.core.set_subject(preparation_id, SUBJECT)
        return self.core.get_preparation(preparation_id)

    def test_another_students_prior_send_to_the_same_supervisor_is_not_a_duplicate(self):
        preparation, _ = self.ready_preparation()
        self.observe(outbound_sent_observation("alex@example.edu"))
        self.assertEqual(self.core.check_duplicate(preparation["id"])["finding"],
                         "duplicate_suspicion")

        other = self.core.create_student("Other Student", "other@163.com")
        other_preparation = self._preparation_for(other["id"])

        self.assertEqual(self.core.get_task(preparation["task_id"])["supervisor_id"],
                         self.core.get_task(other_preparation["task_id"])["supervisor_id"],
                         "both Tasks must address the same Supervisor")
        check = self.core.check_duplicate(other_preparation["id"])
        self.assertEqual(check["finding"], "no_duplicate_found")
        self.assertFalse(check["review_required"])


class LinkedFollowUpTests(DuplicateHistoryTestCase):
    def test_a_linked_follow_up_action_is_not_duplicate_initial_outreach(self):
        _, second_id = self.two_ready_preparations()
        self.observe(outbound_sent_observation("blair@example.edu"))
        self.assertEqual(self.core.check_duplicate(second_id)["finding"],
                         "duplicate_suspicion")

        self.core.link_follow_up(second_id)

        check = self.core.check_duplicate(second_id)
        self.assertEqual(check["finding"], "linked_follow_up")
        self.assertFalse(check["review_required"])
        self.assertEqual(check["matches"], [])


class AmbiguousEvidenceTests(DuplicateHistoryTestCase):
    def ambiguous_preparation(self):
        """Two Supervisors sharing one address leaves the identity unresolved."""
        imported = self.import_bundle(
            [("University_Alex Green.docx",
              draft_paragraphs("shared@example.edu", "Dear Dr Green,", [DECLARATION]))],
            master_rows=[["University", "Alex Green", "shared@example.edu", ""],
                         ["University", "Blair Blue", "shared@example.edu", ""]])
        preparation_id = self.core.prepare_from_documents(imported["id"])["preparation_ids"][0]
        return self.core.get_preparation(preparation_id)

    def test_a_conflicting_supervisor_identity_requires_review(self):
        preparation = self.ambiguous_preparation()

        self.observe(outbound_sent_observation("shared@example.edu"))

        check = self.core.check_duplicate(preparation["id"])
        self.assertEqual(check["finding"], "ambiguous_match")
        self.assertEqual(check["basis"], "conflicting_identity")
        self.assertTrue(check["review_required"])

    def test_confirming_the_identity_resolves_the_conflicting_match(self):
        preparation = self.ambiguous_preparation()
        self.observe(outbound_sent_observation("shared@example.edu"))

        self.core.confirm_task_identity(preparation["task_id"])

        check = self.core.check_duplicate(preparation["id"])
        self.assertEqual(check["finding"], "duplicate_suspicion")
        self.assertEqual(check["basis"], "known_supervisor_address")

    def test_incomplete_observation_evidence_requires_review(self):
        preparation, _ = self.ready_preparation()
        observation = outbound_sent_observation("alex@example.edu")
        observation["messages"][0]["ambiguity"] = "Recipient success could not be established"

        self.observe(observation)

        check = self.core.check_duplicate(preparation["id"])
        self.assertEqual(check["finding"], "ambiguous_match")
        self.assertEqual(check["basis"], "incomplete_evidence")

        self.observe(outbound_sent_observation("alex@example.edu", reference="prior-send-2"))
        resolved = self.core.check_duplicate(preparation["id"])
        self.assertEqual(resolved["finding"], "duplicate_suspicion")
        self.assertEqual(resolved["basis"], "known_supervisor_address")


class ExecutionReconciliationTests(DuplicateHistoryTestCase):
    def test_a_newly_discovered_duplicate_pauses_the_flow_and_submits_nothing(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])

        self.observe(outbound_sent_observation("alex@example.edu"))
        result = self.core.run_execution([confirmation["id"]])

        self.assertTrue(result["paused"])
        self.assertEqual(result["flow"]["state"], "paused")
        self.assertEqual(result["flow"]["reason"], "duplicate_suspicion")
        self.assertEqual(result["attempts"], [])
        self.assertEqual(self.mailbox.requests, [])
        self.assertEqual(self.core.list_execution_attempts(self.campaign["id"]), [])
        self.assertEqual(self.core.get_confirmation(confirmation["id"])["status"], "active")
        self.assertEqual(self.core.execution_status(self.campaign["id"])["reason"],
                         "duplicate_suspicion")
        with self.assertRaises(SmartMailError):
            self.core.run_execution([confirmation["id"]])

    def test_new_ambiguous_evidence_pauses_the_flow_and_submits_nothing(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        observation = outbound_sent_observation("alex@example.edu")
        observation["messages"][0]["ambiguity"] = "Recipient success could not be established"

        self.observe(observation)
        result = self.core.run_execution([confirmation["id"]])

        self.assertEqual(result["flow"]["reason"], "ambiguous_match")
        self.assertEqual(self.mailbox.requests, [])

    def test_a_batch_stops_at_the_duplicated_action(self):
        first_id, second_id = self.two_ready_preparations()
        confirmations = self.core.confirm_preparations([first_id, second_id])
        self.observe(outbound_sent_observation("blair@example.edu"))

        result = self.core.run_execution([c["id"] for c in confirmations])

        self.assertTrue(result["paused"])
        self.assertEqual(len(result["attempts"]), 1)
        self.assertEqual(result["attempts"][0]["preparation_id"], first_id)
        self.assertEqual(len(self.mailbox.requests), 1)
        self.assertEqual(self.core.execution_status(self.campaign["id"])["reason"],
                         "duplicate_suspicion")

    def test_incomplete_coverage_alone_does_not_block_execution(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])

        result = self.core.run_execution([confirmation["id"]])

        self.assertFalse(result["paused"])
        self.assertEqual(len(self.mailbox.requests), 1)
        recorded = self.core.list_duplicate_checks(self.campaign["id"])[-1]
        self.assertEqual(recorded["finding"], "no_duplicate_found")
        self.assertFalse(recorded["evidence_coverage"]["complete"])
        self.assertFalse(recorded["review_required"])


class DuplicatePersistenceTests(DuplicateHistoryTestCase):
    def test_recorded_checks_and_their_coverage_survive_restart(self):
        preparation, _ = self.ready_preparation()
        self.observe(outbound_sent_observation("alex@example.edu"))
        checked = self.core.check_duplicate(preparation["id"])

        self.core.__exit__(None, None, None)
        with SmartMail(self.home) as restarted:
            self.assertEqual(restarted.get_duplicate_check(checked["id"]), checked)
            self.assertEqual(
                [item["id"] for item in restarted.list_duplicate_checks(self.campaign["id"])],
                [checked["id"]])
            self.assertEqual(
                restarted.check_duplicate(preparation["id"])["finding"], "duplicate_suspicion")


class DuplicateTerminalTests(unittest.TestCase):
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

    def build_store(self):
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
        return campaign, student, preparation_id

    def test_terminal_check_inspection_and_execution_use_the_persistent_boundary(self):
        campaign, student, preparation_id = self.build_store()
        confirmed = json.loads(self.run_cli("confirmation", "confirm", preparation_id).stdout)

        observations = self.directory / "observations.json"
        observations.write_text(
            json.dumps({"observations": [outbound_sent_observation("alex@example.edu")]}),
            encoding="utf-8")
        refreshed = self.run_cli(
            "mailbox", "refresh", "--student", student["id"], adapter=observations)
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)

        checked = json.loads(self.run_cli("duplicate", "check", preparation_id).stdout)
        self.assertEqual(checked["finding"], "duplicate_suspicion")
        self.assertEqual(checked["evidence_coverage"]["supervisor_addresses"],
                         ["alex@example.edu"])

        listed = json.loads(self.run_cli(
            "duplicate", "list", "--campaign", campaign["id"]).stdout)
        self.assertEqual([item["id"] for item in listed], [checked["id"]])
        shown = json.loads(self.run_cli("duplicate", "show", checked["id"]).stdout)
        self.assertEqual(shown, checked)

        ran = json.loads(self.run_cli(
            "execution", "run", confirmed[0]["id"],
            adapter=self.script("sent")).stdout)
        self.assertTrue(ran["paused"])
        self.assertEqual(ran["flow"]["reason"], "duplicate_suspicion")
        self.assertEqual(ran["attempts"], [])
        self.assertEqual(json.loads(self.run_cli(
            "execution", "status", "--campaign", campaign["id"]).stdout)["reason"],
            "duplicate_suspicion")

    def script(self, *outcomes):
        path = self.directory / "outcomes.json"
        path.write_text(json.dumps({"outcomes": list(outcomes)}), encoding="utf-8")
        return path


if __name__ == "__main__":
    unittest.main()
