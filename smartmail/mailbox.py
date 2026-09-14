"""Stable imports for Mailbox capabilities and supported adapters."""

from .mailboxes.base import DisabledMailbox, MailboxCapability, MailboxCapabilityError, MailboxCrash
from .mailboxes.controlled import ControlledMailbox
from .mailboxes.extension import NetEase163ExtensionMailbox

__all__ = [
    "DisabledMailbox", "MailboxCapability", "MailboxCapabilityError", "MailboxCrash",
    "ControlledMailbox", "NetEase163ExtensionMailbox",
]
