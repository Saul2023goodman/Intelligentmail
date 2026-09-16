"""Native framing, identity, one-time delivery, deadlines and bounded file transfer."""

import base64
import io
import json
import struct
import tempfile
import unittest
from pathlib import Path

from smartmail.bridge import BridgeError
from smartmail.bridge.install import prepare_installation
from smartmail.bridge.native import NativeSession, read_message, write_message, MAX_INBOUND
from smartmail.bridge.queue import CommandQueue, CHUNK_BYTES


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1000.0
        self.queue = CommandQueue(self.temp.name, clock=lambda: self.now,
                                  validator=lambda operation, payload: None)
        self.queue.connect("session", "student@163.com")

    def enqueue(self, operation="submit", files=()):
        return self.queue.enqueue(operation, "student@163.com", {"subject": "测试"}, files=files, timeout=10)

    def test_only_one_claim_and_permit_even_across_restart(self):
        command_id = self.enqueue()
        self.assertEqual(self.queue.poll("session")["id"], command_id)
        self.assertIsNone(self.queue.poll("session"))
        restarted = CommandQueue(self.temp.name, clock=lambda: self.now,
                                 validator=lambda operation, payload: None)
        self.assertIsNone(restarted.poll("session"))
        self.assertTrue(restarted.authorize("session", command_id)["permitted"])
        with self.assertRaises(BridgeError):
            restarted.authorize("session", command_id)
        restarted.finish("session", command_id, {"outcome": "sent"})
        with self.assertRaises(BridgeError):
            restarted.finish("session", command_id, {"outcome": "sent"})

    def test_stale_and_reconnected_commands_are_not_delivered(self):
        self.enqueue()
        self.now += 11
        self.assertIsNone(self.queue.poll("session"))
        command_id = self.enqueue()
        self.queue.disconnect("session")
        self.queue.connect("new-session", "student@163.com")
        self.assertIsNone(self.queue.poll("new-session"))
        with self.assertRaises(BridgeError):
            self.queue.authorize("new-session", command_id)

    def test_expiry_after_claim_prevents_late_send(self):
        command_id = self.enqueue()
        self.queue.poll("session")
        self.now += 11
        with self.assertRaises(BridgeError):
            self.queue.authorize("session", command_id)

    def test_explicit_mailbox_and_single_connection(self):
        with self.assertRaises(BridgeError):
            self.queue.connect("another", "student@163.com")
        with self.assertRaises(BridgeError):
            self.queue.enqueue("observe", "other@163.com", {})
        self.now += 16
        self.assertFalse(self.queue.status()["connected"])
        with self.assertRaises(BridgeError):
            self.enqueue()

    def test_chunked_attachment_is_exact_and_not_an_arbitrary_path_read(self):
        data = b"\x00\xff\n" * (CHUNK_BYTES // 3 + 77)
        command_id = self.enqueue(files=[data])
        self.queue.poll("session")
        first = self.queue.attachment("session", command_id, 0, 0)
        last = self.queue.attachment("session", command_id, 0, first["next"])
        self.assertEqual(base64.b64decode(first["data"] + last["data"]), data)
        self.assertTrue(last["done"])
        with self.assertRaises(BridgeError):
            self.queue.attachment("session", command_id, "../../file", 0)
        self.queue.expire(command_id)
        with self.assertRaises(BridgeError):
            self.queue.attachment("session", command_id, 0, 0)

    def test_observation_cannot_obtain_send_permit(self):
        command_id = self.enqueue("observe")
        self.queue.poll("session")
        with self.assertRaises(BridgeError):
            self.queue.authorize("session", command_id)

    def test_busy_heartbeat_does_not_claim_the_next_command(self):
        command_id = self.enqueue()
        self.assertIsNone(self.queue.poll("session", ready=False))
        self.assertEqual(self.queue.poll("session")["id"], command_id)

    def test_protocol_rejects_unconnected_and_unknown_messages(self):
        session = NativeSession(self.queue)
        for message in ({"protocol": 2, "type": "connect"}, {"protocol": 1, "type": "poll"},
                        {"protocol": 1, "type": "eval", "code": "anything"}):
            with self.assertRaises(BridgeError):
                session.handle(message)

    def test_utf8_byte_framing_and_truncation(self):
        message = {"text": "邮箱\n中文"}
        stream = io.BytesIO()
        write_message(stream, message)
        self.assertEqual(struct.unpack("=I", stream.getvalue()[:4])[0], len(stream.getvalue()) - 4)
        stream.seek(0)
        self.assertEqual(read_message(stream), message)
        self.assertIsNone(read_message(stream))
        for invalid in (b"\x01", struct.pack("=I", MAX_INBOUND + 1), struct.pack("=I", 5) + b"{}"):
            with self.assertRaises(BridgeError):
                read_message(io.BytesIO(invalid))

    def test_install_manifest_binds_one_extension_and_absolute_store(self):
        result = prepare_installation(Path(self.temp.name) / "space store", "a" * 32, "edge")
        manifest = json.loads(Path(result["manifest"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["allowed_origins"], ["chrome-extension://" + "a" * 32 + "/"])
        self.assertTrue(Path(manifest["path"]).is_absolute())
        self.assertIn("Microsoft\\Edge", result["registry_key"])
        with self.assertRaises(BridgeError):
            prepare_installation(self.temp.name, "*", "chrome")
