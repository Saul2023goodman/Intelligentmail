"""The mailbox adapter boundary: SmartMail's only channel to external execution.

Every external send goes through an adapter. The default adapter has no enabled
capability, so nothing leaves the machine until a capability is separately
verified. A controlled adapter demonstrates outcomes deterministically without
real sends; the 163.com browser adapter attaches through this same boundary.
"""

import json
from pathlib import Path


class MailboxCapabilityError(ValueError):
    """The requested external execution capability is unavailable."""


class MailboxCapability:
    """The adapter boundary: carry out one confirmed request, return observed evidence."""

    name = "unavailable"
    enabled = False

    def submit(self, request: dict) -> dict:
        raise MailboxCapabilityError("No external mailbox capability is enabled")


class DisabledMailbox(MailboxCapability):
    """The default adapter: every capability stays disabled until separately verified."""

    name = "disabled"
    enabled = False

    def submit(self, request: dict) -> dict:
        raise MailboxCapabilityError(
            "External execution is disabled: no verified mailbox capability is enabled")


class ControlledMailbox(MailboxCapability):
    """A deterministic adapter used to demonstrate outcomes without real sends.

    Each ``submit`` records the exact request it received and returns the next
    scripted outcome. Unsupported outcomes are rejected rather than guessed.
    """

    name = "controlled"
    enabled = True
    OUTCOMES = ("sent", "failed", "unknown")

    def __init__(self, outcomes=None, default: str = "sent"):
        self._outcomes = list(outcomes or [])
        self._default = default
        self.requests: list[dict] = []

    def submit(self, request: dict) -> dict:
        self.requests.append(request)
        scripted = self._outcomes.pop(0) if self._outcomes else self._default
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
            return cls(data.get("outcomes", []), default=data.get("default", default))
        return cls(data, default=default)
