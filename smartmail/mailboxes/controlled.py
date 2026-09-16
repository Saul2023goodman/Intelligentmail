"""Deterministic mailbox evidence for development and workflow tests."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .base import MailboxCapability, MailboxCapabilityError, MailboxCrash

_BEIJING = timezone(timedelta(hours=8))


def beijing_stamp(epoch_ms) -> str:
    return datetime.fromtimestamp(epoch_ms / 1000, tz=_BEIJING).strftime("%Y-%m-%d %H:%M:%S")


class ControlledMailbox(MailboxCapability):
    """A deterministic adapter used to demonstrate outcomes without real sends.

    Each ``submit`` records the exact request it received and returns the next
    scripted outcome. Unsupported outcomes are rejected rather than guessed.
    """

    name = "controlled"
    enabled = True
    # Like the real adapter, new capabilities stay unavailable until explicitly opted in.
    schedule_enabled = False
    recall_enabled = False
    OUTCOMES = ("sent", "failed", "unknown", "authentication_required")
    SCHEDULE_OUTCOMES = ("scheduled", "failed", "unknown", "authentication_required")
    CANCEL_OUTCOMES = ("removed", "already_cancelled", "already_sent", "unknown",
                       "failed", "authentication_required")
    RECALL_OUTCOMES = ("recalled", "recall_pending", "recall_failed", "unsupported",
                       "ineligible", "unknown", "failed", "authentication_required")

    def __init__(self, outcomes=None, default: str = "sent", observations=None,
                 schedule_outcomes=None, cancel_outcomes=None, recall_outcomes=None,
                 allow_schedule=False, allow_recall=False):
        self._outcomes = list(outcomes or [])
        self._default = default
        self._observations = list(observations or [])
        self._schedule_outcomes = list(schedule_outcomes or [])
        self._cancel_outcomes = list(cancel_outcomes or [])
        self._recall_outcomes = list(recall_outcomes or [])
        self.schedule_enabled = bool(allow_schedule)
        self.recall_enabled = bool(allow_recall)
        self.requests: list[dict] = []
        self.schedule_requests: list[dict] = []
        self.cancel_requests: list[dict] = []
        self.recall_requests: list[dict] = []
        self.observation_requests: list[str] = []

    def capabilities(self) -> dict:
        capabilities = super().capabilities()
        capabilities["read_history"] = {
            "available": bool(self._observations),
            "verified": False,
            "basis": "controlled fixture; not live platform verification",
        }
        capabilities["immediate_send"] = {
            "available": True,
            "verified": False,
            "basis": "controlled outcome fixture; no external send",
        }
        capabilities["native_scheduling"] = {
            "available": self.schedule_enabled, "verified": False,
            "basis": "controlled schedule fixture; the mailbox does not execute here"
                     if self.schedule_enabled else
                     "Disabled for the controlled adapter; pass allow_schedule for schedule tests",
        }
        capabilities["schedule_cancellation"] = {
            "available": self.schedule_enabled, "verified": False,
            "basis": "controlled cancellation fixture; removal is scripted evidence"
                     if self.schedule_enabled else
                     "Disabled for the controlled adapter; pass allow_schedule for cancellation tests",
        }
        capabilities["recall"] = {
            "available": self.recall_enabled, "verified": False,
            "basis": "controlled Recall fixture; reported separately"
                     if self.recall_enabled else
                     "Disabled for the controlled adapter; pass allow_recall for Recall tests",
        }
        return capabilities

    def observe(self, mailbox_address: str) -> dict:
        self.observation_requests.append(mailbox_address)
        if not self._observations:
            return super().observe(mailbox_address)
        scripted = self._observations.pop(0)
        if not isinstance(scripted, dict):
            raise MailboxCapabilityError("Controlled observation must be a JSON object")
        return {"mailbox_address": mailbox_address, **scripted}

    def submit(self, request: dict, attachments=None) -> dict:
        scripted = self._outcomes.pop(0) if self._outcomes else self._default
        if isinstance(scripted, dict) and scripted.get("crash") == "before_submission":
            raise MailboxCrash("before_submission")
        self.requests.append(request)
        if isinstance(scripted, dict) and scripted.get("crash") == "during_submission":
            raise MailboxCrash("during_submission")
        if isinstance(scripted, dict) and scripted.get("crash") == "after_success":
            evidence = self.evidence(scripted)
            if evidence["outcome"] != "sent":
                raise MailboxCapabilityError(
                    "Controlled after_success crash requires a sent outcome")
            raise MailboxCrash("after_success")
        return self.evidence(scripted)

    @staticmethod
    def _scripted(queue, default, request, allowed, evidence_builder):
        scripted = queue.pop(0) if queue else default
        if isinstance(scripted, str):
            scripted = {"outcome": scripted}
        outcome = scripted.get("outcome", default)
        if outcome not in allowed:
            raise MailboxCapabilityError(f"Unsupported controlled outcome: {outcome}")
        return evidence_builder(outcome, scripted, request)

    def schedule_confirmed(self, request, attachments=None, *, confirmation_id, attempt_id):
        self.schedule_requests.append(request)
        return self._scripted(
            self._schedule_outcomes, "scheduled", request, self.SCHEDULE_OUTCOMES,
            lambda outcome, scripted, request: {
                "outcome": outcome, "reference": scripted.get("external_id", "controlled-schedule-1"),
                "external_id": scripted.get("external_id", "761:controlled-schedule-1"),
                "mailbox_address": request["sender"],
                "detail": scripted.get("detail", ""),
                "evidence": {"folder": "drafts", "schedule_delivery": outcome == "scheduled",
                             "recipient": request["recipient"], "subject": request["subject"],
                             "scheduled_epoch_ms": request["scheduled_epoch_ms"],
                             "scheduled_beijing": scripted.get(
                                 "scheduled_beijing",
                                 beijing_stamp(request["scheduled_epoch_ms"]))}}
            if outcome == "scheduled" else
            {"outcome": outcome, "reference": "", "detail": scripted.get("detail", ""),
             "mailbox_address": request["sender"]})

    def cancel_schedule_confirmed(self, request, *, confirmation_id, attempt_id):
        self.cancel_requests.append(request)
        return self._scripted(
            self._cancel_outcomes, "removed", request, self.CANCEL_OUTCOMES,
            lambda outcome, scripted, request: {
                "outcome": outcome,
                "reference": request.get("external_id", ""),
                "external_id": request.get("external_id", ""),
                "mailbox_address": request["sender"],
                "detail": scripted.get("detail", ""),
                "evidence": scripted.get("evidence", {"external_id": request.get("external_id")})})

    def recall_confirmed(self, request, *, confirmation_id, attempt_id):
        self.recall_requests.append(request)
        return self._scripted(
            self._recall_outcomes, "recalled", request, self.RECALL_OUTCOMES,
            lambda outcome, scripted, request: {
                "outcome": outcome, "reference": request.get("external_id", ""),
                "external_id": request.get("external_id", ""),
                "mailbox_address": request["sender"],
                "detail": scripted.get("detail", ""),
                "evidence": scripted.get("evidence", {"response_code": "S_OK"})})

    @classmethod
    def evidence(cls, scripted) -> dict:
        if isinstance(scripted, str):
            scripted = {"outcome": scripted}
        outcome = scripted.get("outcome", "sent")
        if outcome not in cls.OUTCOMES:
            raise MailboxCapabilityError(f"Unsupported controlled outcome: {outcome}")
        return {"outcome": outcome,
                "reference": scripted.get("reference", f"controlled-{outcome}"),
                "detail": scripted.get("detail", "")}

    @classmethod
    def from_script(cls, path, default: str = "sent") -> "ControlledMailbox":
        """Build a deterministic adapter from an outcome script file (development/testing)."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return cls(data.get("outcomes", []), default=data.get("default", default),
                       observations=data.get("observations", []),
                       schedule_outcomes=data.get("schedule_outcomes", []),
                       cancel_outcomes=data.get("cancel_outcomes", []),
                       recall_outcomes=data.get("recall_outcomes", []),
                       allow_schedule=bool(data.get("allow_schedule", False)),
                       allow_recall=bool(data.get("allow_recall", False)))
        return cls(data, default=default)


