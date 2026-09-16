"""163 webmail commands transported to the installed, explicitly connected extension."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from ..bridge import BridgeError
from ..bridge.queue import CommandQueue
from .base import MailboxCapability, MailboxCapabilityError


class NetEase163ExtensionMailbox(MailboxCapability):
    name = "163-extension"
    needs_attachment_files = True

    def __init__(self, home, *, enable_send=False, enable_schedule=False,
                 enable_recall=False, transport=None, timeout=120):
        self.transport = transport if transport is not None else CommandQueue(home)
        self.enabled = enable_send
        self.schedule_enabled = enable_schedule
        self.recall_enabled = enable_recall
        self.timeout = timeout

    def capabilities(self):
        capabilities = super().capabilities()
        connected = self.transport.status()["connected"]
        capabilities["read_history"] = {
            "available": connected, "verified": False,
            "basis": "Dedicated extension metadata collector; live extension acceptance pending",
        }
        capabilities["immediate_send"] = {
            "available": connected and self.enabled, "verified": False,
            "basis": "Extension acceptance mode explicitly enabled" if self.enabled else
                     "Disabled pending live extension acceptance; --enable-extension-send opts into acceptance mode",
        }
        capabilities["native_scheduling"] = {
            "available": connected and self.schedule_enabled, "verified": False,
            "basis": "Native schedule placement/cancellation accepted with --enable-extension-schedule"
                     if self.schedule_enabled else
                     "Disabled pending live extension acceptance; --enable-extension-schedule opts in",
        }
        capabilities["schedule_cancellation"] = {
            "available": connected and self.schedule_enabled, "verified": False,
            "basis": "Explicit operator Cancellation through the extension under acceptance mode"
                     if self.schedule_enabled else
                     "Disabled pending live extension acceptance; requires explicit Confirmation",
        }
        capabilities["recall"] = {
            "available": connected and self.recall_enabled, "verified": False,
            "basis": "Recall accepted with --enable-extension-recall; outcome is reported separately"
                     if self.recall_enabled else
                     "Disabled by default; platform eligibility requires the full-letter endpoint and "
                     "an explicit --enable-extension-recall acceptance opt-in",
        }
        return capabilities

    @staticmethod
    def _observation(status, detail, mailbox=""):
        return {"status": status, "mailbox_address": mailbox,
                "observed_at": datetime.now(timezone.utc).isoformat(), "detail": detail,
                "coverage": {"folders": [], "complete": False}, "messages": []}

    def observe(self, mailbox_address):
        intended = mailbox_address.lower()
        try:
            result = self.transport.exchange("observe", intended, {"mailbox_address": intended},
                                             timeout=self.timeout)
        except BridgeError as error:
            return self._observation("failed", str(error))
        if not isinstance(result, dict) or result.get("status") not in {
                "complete", "partial", "authentication_required", "wrong_mailbox", "failed"}:
            raise MailboxCapabilityError("Extension returned an unsupported observation")
        actual = str(result.get("mailbox_address", "")).lower()
        if actual != intended and result["status"] in {"complete", "partial", "wrong_mailbox"}:
            return self._observation("wrong_mailbox", f"Connected Mailbox is {actual}; intended Mailbox is {intended}", actual)
        if not isinstance(result.get("messages", []), list) or not isinstance(result.get("coverage", {}), dict):
            raise MailboxCapabilityError("Extension returned malformed observation evidence")
        return result

    def submit(self, request, attachments=None):
        raise MailboxCapabilityError("Use SmartMail confirmed execution; a persisted Execution Attempt is required")

    def _load_files(self, request, attachments):
        descriptors = request.get("attachments", [])
        paths = list(attachments or [])
        if len(paths) != len(descriptors):
            raise MailboxCapabilityError("Confirmed attachment count does not match supplied bytes")
        files = []
        for path, descriptor in zip(paths, descriptors):
            content = Path(path).read_bytes()
            if len(content) != descriptor["size"] or hashlib.sha256(content).hexdigest() != descriptor["sha256"]:
                raise MailboxCapabilityError("Attachment bytes differ from Confirmation")
            files.append(content)
        return files

    def submit_confirmed(self, request, attachments=None, *, confirmation_id, attempt_id):
        if not self.enabled:
            raise MailboxCapabilityError("Extension sending is disabled pending live acceptance")
        if not isinstance(request, dict) or request.get("kind") != "immediate":
            raise MailboxCapabilityError("The extension only accepts confirmed immediate submissions")
        files = self._load_files(request, attachments)
        try:
            payload = {**request, "binding": {"confirmation_id": confirmation_id, "attempt_id": attempt_id}}
            result = self.transport.exchange("submit", request["sender"].lower(), payload,
                                             files=files, timeout=self.timeout)
        except BridgeError as error:
            # No transport exception establishes that a send did not happen.
            return {"outcome": "unknown", "reference": "", "detail": str(error)}
        return self._validated_send(result, request)

    def schedule_confirmed(self, request, attachments=None, *, confirmation_id, attempt_id):
        """Place one confirmed native schedule; the mailbox owns execution afterwards."""
        if not self.schedule_enabled:
            raise MailboxCapabilityError(
                "Native scheduling is disabled; opt in with --enable-extension-schedule for live acceptance")
        if not isinstance(request, dict) or request.get("kind") != "scheduled":
            raise MailboxCapabilityError("The extension only accepts confirmed native schedules")
        epoch_ms = request.get("scheduled_epoch_ms")
        if not isinstance(epoch_ms, int) or epoch_ms <= datetime.now(timezone.utc).timestamp() * 1000:
            raise MailboxCapabilityError("A confirmed future schedule time is required")
        files = self._load_files(request, attachments)
        try:
            payload = {**request, "binding": {"confirmation_id": confirmation_id, "attempt_id": attempt_id}}
            result = self.transport.exchange("schedule", request["sender"].lower(), payload,
                                             files=files, timeout=self.timeout)
        except BridgeError as error:
            return {"outcome": "unknown", "reference": "", "detail": str(error)}
        return self._validated_schedule(result, request)

    def cancel_schedule_confirmed(self, request, *, confirmation_id, attempt_id):
        """Remove one external scheduled draft only after observing the removal."""
        if not self.schedule_enabled:
            raise MailboxCapabilityError(
                "Schedule cancellation is disabled; opt in with --enable-extension-schedule")
        if not isinstance(request, dict) or request.get("kind") != "cancel_schedule":
            raise MailboxCapabilityError("The extension only accepts confirmed schedule cancellation")
        if not request.get("external_id"):
            raise MailboxCapabilityError("Cancellation requires the observed external schedule identity")
        try:
            payload = {**request, "binding": {"confirmation_id": confirmation_id, "attempt_id": attempt_id}}
            result = self.transport.exchange("cancel_schedule", request["sender"].lower(), payload,
                                             timeout=self.timeout)
        except BridgeError as error:
            return {"outcome": "unknown", "reference": "", "detail": str(error)}
        if not isinstance(result, dict) or result.get("outcome") not in {
                "removed", "already_cancelled", "already_sent", "unknown",
                "failed", "authentication_required"}:
            raise MailboxCapabilityError("Extension returned an unsupported cancellation outcome")
        return {"reference": "", "detail": "", **result}

    def recall_confirmed(self, request, *, confirmation_id, attempt_id):
        """Conditional Recall: enabled separately, reported separately, never a completion blocker."""
        if not self.recall_enabled:
            raise MailboxCapabilityError(
                "Recall is disabled by default; opt in with --enable-extension-recall")
        if not isinstance(request, dict) or request.get("kind") != "recall":
            raise MailboxCapabilityError("The extension only accepts a confirmed Recall")
        try:
            payload = {**request, "binding": {"confirmation_id": confirmation_id, "attempt_id": attempt_id}}
            result = self.transport.exchange("recall", request["sender"].lower(), payload,
                                             timeout=self.timeout)
        except BridgeError as error:
            return {"outcome": "unknown", "reference": "", "detail": str(error)}
        if not isinstance(result, dict) or result.get("outcome") not in {
                "recalled", "recall_pending", "recall_failed", "unsupported",
                "ineligible", "unknown", "failed", "authentication_required"}:
            raise MailboxCapabilityError("Extension returned an unsupported Recall outcome")
        return {"reference": "", "detail": "", **result}

    def _validated_send(self, result, request):
        if not isinstance(result, dict) or result.get("outcome") not in {
                "sent", "failed", "unknown", "authentication_required"}:
            raise MailboxCapabilityError("Extension returned an unsupported send outcome")
        if result["outcome"] == "sent":
            evidence = result.get("evidence", {})
            if (not isinstance(evidence, dict) or not result.get("reference")
                    or result.get("mailbox_address", "").lower() != request["sender"].lower()
                    or evidence.get("folder") != "sent" or evidence.get("new_reference") is not True
                    or evidence.get("recipient") != request["recipient"].lower()
                    or evidence.get("subject") != request["subject"]):
                raise MailboxCapabilityError("Sent requires new canonical Sent-folder evidence for the confirmed message")
        return {"reference": "", "detail": "", **result}

    @staticmethod
    def _validated_schedule(result, request):
        if not isinstance(result, dict) or result.get("outcome") not in {
                "scheduled", "failed", "unknown", "authentication_required"}:
            raise MailboxCapabilityError("Extension returned an unsupported schedule outcome")
        if result["outcome"] == "scheduled":
            evidence = result.get("evidence", {})
            external_id = result.get("external_id") or result.get("reference")
            if (not isinstance(evidence, dict) or not external_id
                    or result.get("mailbox_address", "").lower() != request["sender"].lower()
                    or evidence.get("schedule_delivery") is not True
                    or evidence.get("folder") != "drafts"
                    or evidence.get("recipient") != request["recipient"].lower()
                    or evidence.get("subject") != request["subject"]
                    or evidence.get("scheduled_epoch_ms") != request["scheduled_epoch_ms"]):
                raise MailboxCapabilityError(
                    "Scheduled requires observed scheduled-draft evidence for the confirmed message and time")
            result["external_id"] = result["reference"] = external_id
        return {"reference": "", "detail": "", **result}
