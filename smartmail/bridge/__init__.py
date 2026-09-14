"""Local Native Messaging transport for the dedicated mailbox extension."""

PROTOCOL_VERSION = 1
HOST_NAME = "com.smartmail.netease163"


class BridgeError(ValueError):
    """The extension connection or its bounded protocol cannot proceed."""
