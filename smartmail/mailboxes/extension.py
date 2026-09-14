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

    def __init__(self, home, *, enable_send=False, transport=None, timeout=120):
        self.transport = transport if transport is not None else CommandQueue(home)
        self.enabled = enable_send
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

    def submit_confirmed(self, request, attachments=None, *, confirmation_id, attempt_id):
        if not self.enabled:
            raise MailboxCapabilityError("Extension sending is disabled pending live acceptance")
        if not isinstance(request, dict) or request.get("kind") != "immediate":
            raise MailboxCapabilityError("The extension only accepts confirmed immediate submissions")
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
        try:
            payload = {**request, "binding": {"confirmation_id": confirmation_id, "attempt_id": attempt_id}}
            result = self.transport.exchange("submit", request["sender"].lower(), payload,
                                             files=files, timeout=self.timeout)
        except BridgeError as error:
            # No transport exception establishes that a send did not happen.
            return {"outcome": "unknown", "reference": "", "detail": str(error)}
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
