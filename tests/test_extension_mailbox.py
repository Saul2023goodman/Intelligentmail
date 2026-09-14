"""Confirmation -> durable bridge -> extension evidence -> immutable Sent Record."""

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from smartmail import SmartMailError
from smartmail.mailbox import NetEase163ExtensionMailbox, MailboxCapabilityError
from tests.extension_fixture import FixtureExtension
from tests.test_execution import ExecutionTestCase, SUBJECT

ROOT = Path(__file__).resolve().parent.parent


class ExtensionExecutionTests(ExecutionTestCase):
    def connect(self, **kwargs):
        extension = FixtureExtension(self.home, **kwargs)
        self.addCleanup(extension.close)
        self.core.mailbox = NetEase163ExtensionMailbox(self.home, enable_send=True, timeout=2)
        return extension

    def test_confirmed_snapshot_and_attachment_bytes_cross_bridge_and_freeze_sent_record(self):
        preparation, content = self.ready_preparation()
        extension = self.connect()
        confirmation = self.core.confirm(preparation["id"])
        attempt = self.core.run_execution([confirmation["id"]])["attempts"][0]
        self.assertEqual(attempt["state"], "sent")
        self.assertEqual(len(extension.requests), 1)
        self.assertEqual(extension.requests[0]["subject"], SUBJECT)
        self.assertEqual(extension.requests[0]["binding"]["attempt_id"], attempt["id"])
        self.assertEqual(extension.attachments, [[content]])
        sent = self.core.get_sent_record(attempt["sent_record_id"])
        self.assertEqual(self.core.read_sent_attachment(sent["attachments"][0]["id"]), content)
        self.assertEqual(self.core.get_confirmation(confirmation["id"])["status"], "consumed")
        self.assertFalse(extension.errors)

    def test_default_disables_send_and_never_inherits_legacy_verified_status(self):
        self.connect()
        adapter = NetEase163ExtensionMailbox(self.home)
        capabilities = adapter.capabilities()
        self.assertTrue(capabilities["read_history"]["available"])
        self.assertFalse(capabilities["immediate_send"]["available"])
        self.assertTrue(all(not item["verified"] for item in capabilities.values()))
        self.assertFalse(capabilities["native_scheduling"]["available"])
        self.core.mailbox = adapter
        preparation, _ = self.ready_preparation()
        confirmation = self.core.confirm(preparation["id"])
        with self.assertRaises(SmartMailError):
            self.core.run_execution([confirmation["id"]])

    def test_unconfirmed_call_cannot_enqueue(self):
        extension = self.connect()
        with self.assertRaises(MailboxCapabilityError):
            self.core.mailbox.submit({"kind": "immediate"})
        with self.assertRaises(SmartMailError):
            self.core.run_execution(["missing-confirmation"])
        self.assertEqual(extension.requests, [])

    def test_changed_preparation_while_queued_revokes_submission_permit(self):
        preparation, _ = self.ready_preparation()
        def edit():
            with closing(sqlite3.connect(self.home / "smartmail.sqlite3")) as db:
                db.execute("UPDATE preparations SET subject = 'Changed while waiting' WHERE id = ?", (preparation["id"],))
                db.commit()
        self.connect(before_permit=edit)
        confirmation = self.core.confirm(preparation["id"])
        attempt = self.core.run_execution([confirmation["id"]])["attempts"][0]
        self.assertEqual(attempt["state"], "failed")
        self.assertIn("changed", attempt["evidence"]["detail"])
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])

    def test_timeout_after_delivery_stays_unknown_and_is_not_replayed(self):
        preparation, _ = self.ready_preparation()
        extension = self.connect(drop_result=True)
        self.core.mailbox.timeout = 0.3
        confirmation = self.core.confirm(preparation["id"])
        result = self.core.run_execution([confirmation["id"]])
        self.assertEqual(result["attempts"][0]["state"], "unknown")
        self.assertTrue(result["paused"])
        with self.assertRaises(SmartMailError):
            self.core.run_execution([confirmation["id"]])
        self.assertEqual(len(extension.requests), 1)

    def test_sent_without_exact_new_evidence_is_rejected(self):
        preparation, _ = self.ready_preparation()
        self.connect(outcome={"outcome": "sent", "reference": "old-id"})
        confirmation = self.core.confirm(preparation["id"])
        with self.assertRaisesRegex(SmartMailError, "Sent requires"):
            self.core.run_execution([confirmation["id"]])
        self.assertEqual(self.core.list_sent_records(self.campaign["id"]), [])

    def test_read_only_refresh_uses_extension_without_sending(self):
        extension = self.connect()
        result = self.core.refresh_mailbox(self.student["id"])
        self.assertEqual(result["observation"]["status"], "complete")
        self.assertFalse(result["observation"]["evidence_coverage"]["complete"])
        self.assertEqual(extension.requests, [])

    def test_wrong_mailbox_evidence_is_not_imported(self):
        self.connect(observation={"status": "complete", "mailbox_address": "other@163.com", "messages": [{}]})
        result = self.core.refresh_mailbox(self.student["id"])
        self.assertEqual(result["observation"]["status"], "wrong_mailbox")
        self.assertEqual(result["observation"]["messages"], [])

    def test_authentication_pause_never_establishes_sent(self):
        preparation, _ = self.ready_preparation()
        self.connect(outcome={"outcome": "authentication_required", "detail": "Log in again"})
        confirmation = self.core.confirm(preparation["id"])
        result = self.core.run_execution([confirmation["id"]])
        self.assertEqual(result["flow"]["reason"], "authentication_required")
        self.assertEqual(result["attempts"][0]["state"], "unknown")

    def test_unknown_then_explicit_reconciliation_resolves_without_another_send(self):
        preparation, _ = self.ready_preparation()
        extension = self.connect(outcome={"outcome": "unknown", "detail": "No Sent evidence yet"})
        confirmation = self.core.confirm(preparation["id"])
        attempt = self.core.run_execution([confirmation["id"]])["attempts"][0]
        self.core.take_over_execution(attempt["id"])
        result = self.core.reconcile_and_continue(attempt["id"])
        self.assertTrue(result["resolved"])
        self.assertEqual(result["attempt"]["state"], "sent")
        self.assertEqual(len(extension.requests), 1)

    def test_native_scheduling_is_still_disabled(self):
        preparation, _ = self.ready_preparation()
        extension = self.connect()
        confirmation = self.core.confirm(preparation["id"], execution={"kind": "scheduled", "scheduled_at": "2099-01-01T09:00:00Z"})
        with self.assertRaises(SmartMailError):
            self.core.run_execution([confirmation["id"]])
        self.assertEqual(extension.requests, [])


class ExtensionTerminalTests(unittest.TestCase):
    def test_new_adapter_is_disconnected_by_default_and_legacy_option_is_rejected(self):
        with tempfile.TemporaryDirectory() as home:
            prefix = [sys.executable, "-m", "smartmail", "--home", home]
            result = subprocess.run([*prefix, "--adapter", "163-extension", "mailbox", "capabilities"],
                                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["adapter"], "163-extension")
            self.assertFalse(data["capabilities"]["immediate_send"]["available"])
            old = subprocess.run([*prefix, "--adapter", "163-browser", "mailbox", "capabilities"],
                                 cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(old.returncode, 2)
