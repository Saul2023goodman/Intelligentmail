"""Deterministic mailbox evidence for development and workflow tests."""

import json
from pathlib import Path

from .base import MailboxCapability, MailboxCapabilityError, MailboxCrash


class ControlledMailbox(MailboxCapability):
    """A deterministic adapter used to demonstrate outcomes without real sends.

    Each ``submit`` records the exact request it received and returns the next
    scripted outcome. Unsupported outcomes are rejected rather than guessed.
    """

    name = "controlled"
    enabled = True
    OUTCOMES = ("sent", "failed", "unknown", "authentication_required")

    def __init__(self, outcomes=None, default: str = "sent", observations=None):
        self._outcomes = list(outcomes or [])
        self._default = default
        self._observations = list(observations or [])
        self.requests: list[dict] = []
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
                       observations=data.get("observations", []))
        return cls(data, default=default)


