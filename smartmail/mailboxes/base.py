"""External Mailbox capability interface and disabled adapter."""

class MailboxCapabilityError(ValueError):
    """The requested external execution capability is unavailable."""


class MailboxCrash(RuntimeError):
    """A controlled process-boundary interruption for recovery acceptance tests."""

    def __init__(self, phase: str):
        self.phase = phase
        super().__init__(f"controlled process crash: {phase}")


class MailboxCapability:
    """The adapter boundary: carry out one confirmed request, return observed evidence."""

    name = "unavailable"
    enabled = False

    _CAPABILITIES = (
        "read_history", "immediate_send", "native_scheduling",
        "schedule_cancellation", "recall",
    )

    def capabilities(self) -> dict:
        """Report each platform capability independently.

        ``enabled`` remains the execution-send guard used by ticket 05. Reading
        a mailbox never turns it on.
        """
        return {
            capability: {
                "available": False,
                "verified": False,
                "basis": "not enabled for this adapter",
            }
            for capability in self._CAPABILITIES
        }

    def observe(self, mailbox_address: str) -> dict:
        return {
            "status": "unsupported",
            "mailbox_address": mailbox_address,
            "detail": "Read-only mailbox history is not available for this adapter",
            "coverage": {"folders": [], "complete": False},
            "messages": [],
        }

    #: Whether an adapter needs the confirmed attachment bytes materialized to
    #: private files before submission. The controlled adapter does not; the
    #: extension adapter transfers verified bytes through Native Messaging.
    needs_attachment_files = False

    def submit(self, request: dict, attachments=None) -> dict:
        raise MailboxCapabilityError("No external mailbox capability is enabled")

    def submit_confirmed(self, request, attachments, *, confirmation_id, attempt_id):
        """Carry persisted execution identity to adapters that recheck authority."""
        return self.submit(request, attachments)


class DisabledMailbox(MailboxCapability):
    """The default adapter: every capability stays disabled until separately verified."""

    name = "disabled"
    enabled = False

    def submit(self, request: dict, attachments=None) -> dict:
        raise MailboxCapabilityError(
            "External execution is disabled: no verified mailbox capability is enabled")


