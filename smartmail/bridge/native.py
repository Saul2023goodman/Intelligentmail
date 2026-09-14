"""Length-prefixed Native Messaging; stdout contains protocol frames only."""

import json
import struct
from uuid import uuid4

from . import BridgeError, PROTOCOL_VERSION

MAX_INBOUND = 32 * 1024 * 1024
MAX_OUTBOUND = 1024 * 1024


def read_exact(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.read(size - len(data))
        if not chunk:
            raise BridgeError("Truncated Native Messaging frame")
        data.extend(chunk)
    return bytes(data)


def read_message(stream):
    first = stream.read(1)
    if not first:
        return None
    size = struct.unpack("=I", first + read_exact(stream, 3))[0]
    if not 0 < size <= MAX_INBOUND:
        raise BridgeError("Native Messaging frame exceeds the supported limit")
    try:
        message = json.loads(read_exact(stream, size))
    except (ValueError, UnicodeError) as error:
        raise BridgeError("Invalid Native Messaging JSON") from error
    if not isinstance(message, dict):
        raise BridgeError("Native Messaging request must be an object")
    return message


def write_message(stream, message):
    data = json.dumps(message, ensure_ascii=False).encode("utf-8")
    if len(data) > MAX_OUTBOUND:
        raise BridgeError("Native Messaging response exceeds 1 MiB")
    stream.write(struct.pack("=I", len(data)) + data)
    stream.flush()


class NativeSession:
    def __init__(self, queue):
        self.queue = queue
        self.id = str(uuid4())
        self.connected = False

    def handle(self, message):
        if message.get("protocol") != PROTOCOL_VERSION:
            raise BridgeError("Unsupported extension protocol version")
        operation = message.get("type")
        if operation == "connect":
            from ..identity import email_address
            mailbox = email_address(message.get("mailbox_address", ""))
            if not mailbox or not mailbox.endswith("@163.com") or self.connected:
                raise BridgeError("Connect exactly one authenticated 163 Mailbox per port")
            self.queue.connect(self.id, mailbox)
            self.connected = True
            return {"connected": True, "mailbox_address": mailbox}
        if not self.connected:
            raise BridgeError("Connect a Mailbox before requesting work")
        if operation == "poll":
            return {"command": self.queue.poll(self.id, ready=message.get("ready", True) is True)}
        if operation == "attachment":
            return self.queue.attachment(self.id, message.get("command_id"),
                                         message.get("position"), message.get("offset"))
        if operation == "authorize":
            return self.queue.authorize(self.id, message.get("command_id"))
        if operation == "result":
            self.queue.finish(self.id, message.get("command_id"), message.get("result"))
            return {"recorded": True}
        raise BridgeError("Unsupported Native Messaging request")

    def serve(self, input_stream, output_stream):
        try:
            while (message := read_message(input_stream)) is not None:
                response = {"protocol": PROTOCOL_VERSION, "id": message.get("id")}
                try:
                    response.update({"ok": True, "result": self.handle(message)})
                except (BridgeError, TypeError, ValueError) as error:
                    response.update({"ok": False, "error": str(error)})
                write_message(output_stream, response)
        finally:
            self.queue.disconnect(self.id)
