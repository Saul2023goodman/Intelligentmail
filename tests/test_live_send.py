"""Ticket 09: operator-confirmed immediate sending through the live 163.com adapter.

These tests exercise the enabled live adapter through the same command/query
boundary the terminal shell uses, with a deterministic stand-in for the
Playwright CLI.  They verify the exact confirmed snapshot, evidence-based
Sent, pause and recovery behaviour without a live account.  The real 163.com
page is exercised separately in controlled live acceptance.
"""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

from smartmail import SmartMailError
from smartmail.mailbox import NetEase163Mailbox
from tests.test_execution import ExecutionTestCase, SUBJECT

ROOT = Path(__file__).resolve().parent.parent
SESSION = "smartmail-163"


def envelope(payload) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["playwright-cli"], returncode=0,
        stdout=json.dumps({"result": json.dumps(payload)}), stderr="")


def observed_sent(counterpart="alex@example.edu", subject=SUBJECT, reference="163-sent-1"):
    return {
        "status": "complete",
        "mailbox_address": "student@163.com",
        "observed_at": "2026-09-11T07:30:00+00:00",
        "coverage": {"complete": False, "folders": []},
        "messages": [{
            "direction": "outbound", "folder": "sent", "platform_reference": reference,
            "counterpart": counterpart, "subject": subject,
            "observed_time": "2026年9月11日 16:00", "status": "sent", "ambiguity": "",
            "evidence": {"marker": "发送成功"},
        }],
    }


class FakePlaywrightRunner:
    """Deterministic stand-in for the Playwright CLI invoked by the 163 adapter."""

    INJECTION_RE = re.compile(
        r"const request = (\{.*?\});\n  const attachmentFiles = (\[.*?\]);", re.S)

    def __init__(self, outcomes=(), observations=(), unavailable=False):
        self.outcomes = list(outcomes)
        self.observations = list(observations)
        self.unavailable = unavailable
        self.commands: list[list[str]] = []
        self.requests: list[dict] = []
        self.attachment_bytes: list[list[bytes]] = []
        self.attachment_paths: list[list[Path]] = []
        self.opened = 0

    def __call__(self, command, capture_output=True, text=True, encoding="utf-8", timeout=None):
        self.commands.append(list(command))
        if "run-code" not in command:
            self.opened += 1
            return subprocess.CompletedProcess(list(command), 0, "", "")
        if self.unavailable:
            return subprocess.CompletedProcess(
                list(command), 1, "", "Browser is not open. Run 'open' first.")
        code = command[-1]
        if "const request = " in code:
            match = self.INJECTION_RE.search(code)
            if match is None:
                raise AssertionError("The confirmed request literal was not injected")
            self.requests.append(json.loads(match.group(1)))
            files = [Path(item) for item in json.loads(match.group(2))]
            self.attachment_bytes.append([path.read_bytes() for path in files])
            self.attachment_paths.append(files)
            outcome = self.outcomes.pop(0) if self.outcomes else "sent"
            if isinstance(outcome, str):
                outcome = {"outcome": outcome, "reference": "163-sent-1"}
            return envelope(outcome)
        observation = self.observations.pop(0) if self.observations else {
            "status": "complete", "mailbox_address": "student@163.com",
            "coverage": {"folders": [], "complete": False}, "messages": []}
        return envelope(observation)


class LiveImmediateSendTests(ExecutionTestCase):
    def live(self, **kwargs):
        runner = FakePlaywrightRunner(**kwargs)
        return NetEase163Mailbox(session=SESSION, runner=runner), runner

    def test_confirmed_send_is_sent_only_with_mailbox_evidence_and_freezes_the_record(self):
        preparation, cv_bytes = self.ready_preparation()
        adapter, runner = self.live()
        self.core.mailbox = adapter
        confirmation = self.core.confirm(preparation["id"])

        result = self.core.run_execution([confirmation["id"]])

        attempt = result["attempts"][0]
        self.assertEqual(attempt["state"], "sent")
        self.assertFalse(result["paused"])
        self.assertEqual(result["flow"]["state"], "idle")
        # The exact confirmed snapshot, and nothing else, reached the adapter.
        self.assertEqual(len(runner.requests), 1)
        request = runner.requests[0]
        self.assertEqual(request["sender"], "student@163.com")
        self.assertEqual(request["recipient"], "alex@example.edu")
        self.assertEqual(request["subject"], SUBJECT)
        self.assertEqual(request["kind"], "immediate")
        self.assertEqual(request["attachments"][0]["name"], "Test Student - CV.docx")
        # The adapter uploaded the exact confirmed bytes from a private copy.
        self.assertEqual(runner.attachment_bytes[0], [cv_bytes])
        # The private copies are removed once the single submission returns.
        self.assertTrue(runner.attachment_paths[0])
        self.assertTrue(all(not path.exists() for path in runner.attachment_paths[0]))
        # The Sent Record is frozen and the Confirmation is consumed.
        sent = self.core.get_sent_record(attempt["sent_record_id"])
        self.assertEqual(sent["subject"], SUBJECT)
        self.assertEqual(sent["reference"], "163-sent-1")
        self.assertEqual(self.core.read_sent_attachment(sent["attachments"][0]["id"]), cv_bytes)
        self.assertEqual(self.core.get_confirmation(confirmation["id"])["status"], "consumed")

    def test_capabilities_enable_immediate_send_but_keep_scheduling_disabled(self):
        capabilities = NetEase163Mailbox(session=SESSION, runner=FakePlaywrightRunner()).capabilities()

        self.assertTrue(capabilities["read_history"]["available"])
        self.assertTrue(capabilities["immediate_send"]["available"])
        self.assertTrue(capabilities["immediate_send"]["verified"])
        for capability in ("native_scheduling", "schedule_cancellation", "recall"):
            self.assertFalse(capabilities[capability]["available"])

    def test_authentication_interruption_pauses_without_marking_sent(self):
        preparation, _ = self.ready_preparation()
        adapter, runner = self.live(outcomes=[{
            "outcome": "authentication_required",
            "detail": "Complete login then run execution again"}])
        self.core.mailbox = adapter
        confirmation = self.core.confirm(preparation["id"])

        result = self.core.run_execution([confirmation["id"]])

        self.assertTrue(result["paused"])
        self.assertEqual(result["flow"]["reason"], "authentication_required")
        self.assertEqual(result["attempts"][0]["state"], "unknown")
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])
        self.assertEqual(self.core.get_confirmation(confirmation["id"])["status"], "active")

    def test_a_closed_browser_is_opened_and_handed_to_the_operator(self):
        preparation, _ = self.ready_preparation()
        adapter, runner = self.live(unavailable=True)
        self.core.mailbox = adapter
        confirmation = self.core.confirm(preparation["id"])

        result = self.core.run_execution([confirmation["id"]])

        self.assertEqual(result["flow"]["reason"], "authentication_required")
        self.assertEqual(runner.opened, 1, "the headed browser should be opened once")
        self.assertEqual(runner.requests, [], "nothing may be submitted before authentication")

    def test_a_closed_browser_opens_a_persistent_profile_for_reusable_login(self):
        """The operator login must survive daemon restarts, so a closed browser is
        opened with a persistent user-data directory rather than an ephemeral one."""
        preparation, _ = self.ready_preparation()
        adapter, runner = self.live(unavailable=True)
        self.core.mailbox = adapter
        confirmation = self.core.confirm(preparation["id"])

        result = self.core.run_execution([confirmation["id"]])

        self.assertEqual(result["flow"]["reason"], "authentication_required")
        open_command = runner.commands[-1]
        self.assertIn("-s=smartmail-163", open_command)
        self.assertIn("open", open_command)
        self.assertIn("--persistent", open_command)
        self.assertIn("--profile", open_command)
        self.assertIn(str(adapter.profile), open_command)
        self.assertIn("--headed", open_command)

    def test_the_send_payload_tolerates_late_editors_and_native_dialogs(self):
        """Two live-account obstacles must stay handled: the rich-text body editor
        initialises after the rest of the compose form, and a native dialog left
        open blocks the CLI's evaluation context for every later command."""
        payload = (ROOT / "smartmail" / "netease_163_sender.js").read_text(encoding="utf-8")

        # The body editor is polled until it appears rather than sampled once.
        self.assertIn("bodyDeadline", payload)
        self.assertIn("APP-editor-textarea", payload)
        # Native dialogs are accepted as they appear and their text is reported.
        self.assertIn('on("dialog"', payload)
        self.assertIn("dialog.accept()", payload)
        self.assertIn("dialogs: dialogLog", payload)
        # Both outcomes carry the acknowledged dialogs for the Execution Ledger.
        self.assertEqual(payload.count("dialogs: dialogLog"), 2)

    def test_a_failure_pauses_the_flow_and_records_evidence(self):
        preparation, _ = self.ready_preparation()
        adapter, _ = self.live(outcomes=[{"outcome": "failed", "detail": "recipient rejected"}])
        self.core.mailbox = adapter
        confirmation = self.core.confirm(preparation["id"])

        result = self.core.run_execution([confirmation["id"]])

        self.assertTrue(result["paused"])
        self.assertEqual(result["flow"]["reason"], "execution_failed")
        self.assertEqual(result["attempts"][0]["state"], "failed")
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])

    def test_an_unconfirmed_submission_stays_unknown_and_is_not_recorded_sent(self):
        preparation, _ = self.ready_preparation()
        adapter, _ = self.live(outcomes=[{"outcome": "unknown", "detail": "no Sent evidence"}])
        self.core.mailbox = adapter
        confirmation = self.core.confirm(preparation["id"])

        result = self.core.run_execution([confirmation["id"]])

        self.assertTrue(result["paused"])
        self.assertEqual(result["flow"]["reason"], "unknown_outcome")
        attempt = result["attempts"][0]
        self.assertEqual(attempt["state"], "unknown")
        self.assertIsNone(attempt["sent_record_id"])
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])

    def test_native_scheduling_is_refused_even_with_an_active_confirmation(self):
        preparation, _ = self.ready_preparation()
        adapter, runner = self.live()
        self.core.mailbox = adapter
        confirmation = self.core.confirm(
            preparation["id"], execution={"kind": "scheduled", "scheduled_at": "2026-09-12T09:00"})

        with self.assertRaises(SmartMailError):
            self.core.run_execution([confirmation["id"]])

        self.assertEqual(runner.requests, [], "an unverified execution kind must not submit")

    def test_no_submission_happens_without_an_applicable_confirmation(self):
        preparation, _ = self.ready_preparation()
        adapter, runner = self.live()
        self.core.mailbox = adapter

        with self.assertRaises(SmartMailError):
            self.core.run_execution(["unknown-confirmation"])

        self.assertEqual(runner.requests, [])
        self.assertEqual(self.core.list_execution_attempts(self.campaign["id"]), [])

    def test_an_unsupported_adapter_outcome_is_rejected_without_a_sent_record(self):
        preparation, _ = self.ready_preparation()
        adapter, _ = self.live(outcomes=[{"outcome": "maybe"}])
        self.core.mailbox = adapter
        confirmation = self.core.confirm(preparation["id"])

        with self.assertRaises(SmartMailError):
            self.core.run_execution([confirmation["id"]])

        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])

    def test_unknown_outcome_then_takeover_reconciles_before_recording_sent(self):
        preparation, _ = self.ready_preparation()
        adapter, _ = self.live(
            outcomes=[{"outcome": "unknown", "detail": "connection lost"}],
            observations=[observed_sent()])
        self.core.mailbox = adapter
        confirmation = self.core.confirm(preparation["id"])
        attempt = self.core.run_execution([confirmation["id"]])["attempts"][0]

        takeover = self.core.take_over_execution(attempt["id"], detail="operator checked 163.com")
        self.assertEqual(takeover["state"], "unknown")
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])

        reconciled = self.core.reconcile_and_continue(attempt["id"])

        self.assertTrue(reconciled["resolved"])
        self.assertEqual(reconciled["attempt"]["state"], "sent")
        sent = self.core.get_sent_record(reconciled["attempt"]["sent_record_id"])
        self.assertEqual(sent["reference"], "163-sent-1")
        self.assertEqual(self.core.get_confirmation(confirmation["id"])["status"], "consumed")
        self.assertEqual(self.core.execution_status(self.campaign["id"])["state"], "idle")


class LiveAdapterTerminalTests(unittest.TestCase):
    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "smartmail", "--adapter", "163-browser",
             "--browser-session", SESSION, *arguments],
            cwd=ROOT, capture_output=True, text=True, encoding="utf-8")

    def test_terminal_reports_immediate_send_enabled_and_scheduling_disabled(self):
        result = self.run_cli("mailbox", "capabilities")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["adapter"], "163-browser")
        self.assertTrue(payload["capabilities"]["immediate_send"]["available"])
        self.assertTrue(payload["capabilities"]["immediate_send"]["verified"])
        self.assertFalse(payload["capabilities"]["native_scheduling"]["available"])


if __name__ == "__main__":
    unittest.main()
