"""Ticket 06: persisted read-only mailbox observations and manual Reconciliation."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from smartmail import SmartMail
from smartmail.mailbox import ControlledMailbox, NetEase163ExtensionMailbox
from tests.test_execution import ExecutionTestCase, SUBJECT


ROOT = Path(__file__).parents[1]


def observed_history(mailbox="student@163.com"):
    return {
        "status": "complete",
        "mailbox_address": mailbox,
        "observed_at": "2026-09-11T07:30:00+00:00",
        "detail": "controlled first-page observation",
        "coverage": {
            "complete": False,
            "folders": [
                {"folder": "inbox", "page_scope": "first_visible_page",
                 "pages_observed": 1, "messages_observed": 1, "complete": False},
                {"folder": "sent", "page_scope": "first_visible_page",
                 "pages_observed": 1, "messages_observed": 1, "complete": False},
            ],
        },
        "messages": [
            {"direction": "inbound", "folder": "inbox", "platform_reference": "in-1",
             "counterpart": "supervisor@example.edu", "subject": "Re: Research",
             "observed_time": "2026年9月11日 14:00", "status": "received",
             "evidence": {"aria_label": "Re: Research 发件人 ： supervisor 时间： ..."}},
            {"direction": "outbound", "folder": "sent", "platform_reference": "out-1",
             "counterpart": "supervisor@example.edu", "subject": "Research",
             "observed_time": "2026年9月10日 10:00", "status": "sent",
             "evidence": {"aria_label": "Research 收件人 ： supervisor 时间： ...",
                          "marker": "发送成功"}},
        ],
    }


class ReconciliationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "state"
        self.adapter = ControlledMailbox(observations=[observed_history()])
        self.core = SmartMail(self.home, mailbox=self.adapter)
        self.addCleanup(self.core.__exit__, None, None, None)
        self.student = self.core.create_student("Test Student", "student@163.com")

    def test_manual_refresh_persists_observations_coverage_and_reconciliation(self):
        refreshed = self.core.refresh_mailbox(self.student["id"])

        observation = refreshed["observation"]
        self.assertEqual(observation["status"], "complete")
        self.assertFalse(observation["evidence_coverage"]["complete"])
        self.assertEqual([message["folder"] for message in observation["messages"]],
                         ["inbox", "sent"])
        self.assertEqual(observation["messages"][1]["platform_reference"], "out-1")
        self.assertEqual(self.adapter.observation_requests, ["student@163.com"])
        self.assertEqual(self.adapter.requests, [], "read-only refresh must not submit a send")

        reconciliation = refreshed["reconciliation"]
        self.assertEqual(reconciliation["summary"]["messages_observed"], 2)
        self.assertFalse(reconciliation["summary"]["local_state_changed"])
        self.assertEqual(
            {finding["finding"] for finding in reconciliation["findings"]},
            {"unassociated_inbound", "unassociated_outbound"})

        observation_id = observation["id"]
        reconciliation_id = reconciliation["id"]
        self.core.__exit__(None, None, None)
        with SmartMail(self.home) as restarted:
            self.assertEqual(restarted.get_mailbox_observation(observation_id)["messages"],
                             observation["messages"])
            self.assertEqual(restarted.get_reconciliation(reconciliation_id), reconciliation)
            self.assertEqual(len(restarted.list_mailbox_observations(self.student["id"])), 1)

    def test_wrong_mailbox_is_persisted_without_importing_its_messages(self):
        self.core.mailbox = ControlledMailbox(observations=[observed_history("other@163.com")])

        refreshed = self.core.refresh_mailbox(self.student["id"])

        observation = refreshed["observation"]
        self.assertEqual(observation["status"], "wrong_mailbox")
        self.assertEqual(observation["messages"], [])
        self.assertIn("intended Mailbox", observation["detail"])
        self.assertEqual(refreshed["reconciliation"]["findings"][0]["finding"],
                         "observation_unavailable")

    def test_unsupported_and_ambiguous_observations_remain_explicit(self):
        self.core.mailbox = ControlledMailbox(observations=[{
            "status": "partial", "coverage": {"complete": False},
            "messages": [{"direction": "unknown", "status": "mystery",
                          "evidence": "unsupported raw form"}],
        }])

        refreshed = self.core.refresh_mailbox(self.student["id"])

        message = refreshed["observation"]["messages"][0]
        self.assertEqual(message["direction"], "ambiguous")
        self.assertEqual(message["status"], "ambiguous")
        self.assertTrue(message["ambiguity"])
        self.assertEqual(refreshed["reconciliation"]["findings"][0]["finding"],
                         "ambiguous_observation")

    def test_capabilities_are_independent_and_read_does_not_enable_writes(self):
        controlled = self.core.mailbox_capabilities()["capabilities"]
        self.assertTrue(controlled["read_history"]["available"])
        self.assertFalse(controlled["read_history"]["verified"])
        self.assertTrue(controlled["immediate_send"]["available"])
        self.assertFalse(controlled["native_scheduling"]["available"])

        live = NetEase163ExtensionMailbox(self.home).capabilities()
        self.assertFalse(live["read_history"]["available"], "an extension must be connected explicitly")
        self.assertFalse(live["read_history"]["verified"], "legacy acceptance does not verify the extension")
        self.assertFalse(live["immediate_send"]["available"])
        for capability in ("native_scheduling", "schedule_cancellation", "recall"):
            self.assertFalse(live[capability]["available"])

    def test_folder_scan_coverage_and_non_delivery_states_are_preserved(self):
        observation = observed_history()
        observation["coverage"] = {
            "complete": False,
            "supported_scope_complete": True,
            "folder_discovery": {
                "method": "live_dom", "expected_recognized": 5, "complete": True,
                "recognized": [
                    {"folder": folder, "folder_id": fid}
                    for fid, folder in enumerate(
                        ("inbox", "drafts", "sent", "deleted", "spam"), start=1)
                ],
            },
            "folders": [{
                "folder": "drafts", "folder_id": 2, "declared_total": 1,
                "ids_enumerated": 1, "pages_requested": 1, "pages_succeeded": 1,
                "details_requested": 1, "details_succeeded": 1, "details_failed": 0,
                "enumeration_complete": True, "detail_complete": True, "complete": True,
            }],
        }
        observation["messages"] = [{
            "direction": "outbound", "folder": "drafts",
            "platform_reference": "canonical-draft-id", "counterpart": "draft@example.edu",
            "subject": "Unsent draft", "observed_time": "2026-09-11 15:51:05",
            "status": "draft",
            "evidence": {
                "source": "list plus metadata detail",
                "detail": {"subject": "Unsent draft", "attachments": []},
                "body": {"fetched": False, "reason": "preserve unread state"},
            },
        }]
        self.core.mailbox = ControlledMailbox(observations=[observation])

        refreshed = self.core.refresh_mailbox(self.student["id"])

        persisted = refreshed["observation"]
        self.assertTrue(persisted["evidence_coverage"]["supported_scope_complete"])
        self.assertEqual(persisted["messages"][0]["status"], "draft")
        self.assertEqual(
            persisted["messages"][0]["evidence"]["detail"]["attachments"], [])
        finding = refreshed["reconciliation"]["findings"][0]
        self.assertEqual(finding["finding"], "observed_non_delivery_state")
        self.assertIn("not evidence of delivery", finding["detail"])


class ReconciliationMatchTests(ExecutionTestCase):
    @staticmethod
    def outbound_observation(reference=""):
        observation = observed_history()
        observation["messages"] = [{
            "direction": "outbound", "folder": "sent",
            "platform_reference": reference, "counterpart": "alex@example.edu",
            "subject": SUBJECT, "observed_time": "2026年9月11日 10:00",
            "status": "sent", "evidence": {"marker": "发送成功"},
        }]
        observation["coverage"]["folders"] = [
            {"folder": "sent", "page_scope": "first_visible_page",
             "pages_observed": 1, "messages_observed": 1, "complete": False}]
        return observation

    def test_exact_platform_reference_links_observation_to_a_sent_record(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        sent = self.core.run_execution([confirmation["id"]])["attempts"][0]
        self.core.mailbox = ControlledMailbox(
            observations=[self.outbound_observation("controlled-sent")])

        reconciliation = self.core.refresh_mailbox(self.student["id"])["reconciliation"]

        finding = reconciliation["findings"][0]
        self.assertEqual(finding["finding"], "matched_sent_record")
        self.assertEqual(finding["local_id"], sent["sent_record_id"])
        self.assertEqual(finding["basis"], "platform_reference")
        self.assertFalse(reconciliation["summary"]["local_state_changed"])

    def test_exact_list_fields_link_but_do_not_resolve_an_unknown_attempt(self):
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        self.script({"outcome": "unknown", "detail": "connection lost"})
        attempt = self.core.run_execution([confirmation["id"]])["attempts"][0]
        self.core.mailbox = ControlledMailbox(
            observations=[self.outbound_observation()])

        reconciliation = self.core.refresh_mailbox(self.student["id"])["reconciliation"]

        finding = reconciliation["findings"][0]
        self.assertEqual(finding["finding"], "matched_unresolved_attempt")
        self.assertEqual(finding["local_id"], attempt["id"])
        self.assertEqual(self.core.get_execution_attempt(attempt["id"])["state"], "unknown")
        self.assertFalse(reconciliation["summary"]["local_state_changed"])


class ReconciliationTerminalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.home = self.directory / "state"

    def run_cli(self, *arguments, adapter_script=None):
        prefix = [sys.executable, "-m", "smartmail", "--home", str(self.home)]
        if adapter_script:
            prefix += ["--adapter", "controlled", "--adapter-script", str(adapter_script)]
        return subprocess.run(
            [*prefix, *arguments], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def test_terminal_refresh_and_inspection_use_the_persistent_boundary(self):
        student = json.loads(self.run_cli(
            "student", "create", "Test Student", "--mailbox", "student@163.com").stdout)
        script = self.directory / "observations.json"
        script.write_text(json.dumps({"observations": [observed_history()]}), encoding="utf-8")

        refreshed_process = self.run_cli(
            "mailbox", "refresh", "--student", student["id"], adapter_script=script)
        self.assertEqual(refreshed_process.returncode, 0, refreshed_process.stderr)
        refreshed = json.loads(refreshed_process.stdout)
        observation_id = refreshed["observation"]["id"]
        reconciliation_id = refreshed["reconciliation"]["id"]

        shown = json.loads(self.run_cli("mailbox", "show", observation_id).stdout)
        self.assertEqual(len(shown["messages"]), 2)
        listed = json.loads(self.run_cli(
            "mailbox", "observations", "--student", student["id"]).stdout)
        self.assertEqual([item["id"] for item in listed], [observation_id])
        reconciled = json.loads(self.run_cli(
            "reconciliation", "show", reconciliation_id).stdout)
        self.assertEqual(reconciled["summary"]["messages_observed"], 2)


if __name__ == "__main__":
    unittest.main()
