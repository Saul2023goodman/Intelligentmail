"""Durable, single-delivery commands shared by CLI and browser native host.

This database is transport state, separate from SmartMail's Execution Ledger.
Claimed commands are never put back on the queue, including after a crash.
"""

import base64
import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from . import BridgeError, PROTOCOL_VERSION

LEASE_SECONDS = 15
CHUNK_BYTES = 192 * 1024
MAX_COMMAND_BYTES = 512 * 1024
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024

#: External operations that change sending commitment require a consumed permit.
PERMITTED_OPERATIONS = {"submit", "schedule", "cancel_schedule", "recall"}
#: Adapter outcomes that prove an external mutation happened; they require a permit.
PERMITTED_OUTCOMES = {
    "submit": {"sent"},
    "schedule": {"scheduled"},
    "cancel_schedule": {"removed", "already_cancelled", "already_sent"},
    "recall": {"recalled", "recall_pending"},
}


class CommandQueue:
    def __init__(self, home, clock=time.time, validator=None):
        self.path = Path(home).resolve() / "extension-bridge.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        from .authorization import validate_command
        self.validate = validator or (
            lambda operation, payload: validate_command(self.path.parent, operation, payload))
        with self._connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS connection (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    session TEXT NOT NULL, mailbox TEXT NOT NULL, seen REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commands (
                    id TEXT PRIMARY KEY, session TEXT NOT NULL, operation TEXT NOT NULL,
                    payload TEXT NOT NULL, deadline REAL NOT NULL, state TEXT NOT NULL,
                    result TEXT, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS files (
                    command_id TEXT NOT NULL, position INTEGER NOT NULL, content BLOB NOT NULL,
                    PRIMARY KEY(command_id, position)
                );
            """)

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def connect(self, session, mailbox):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM connection").fetchone()
            if old and old["session"] != session and old["seen"] > self.clock() - LEASE_SECONDS:
                raise BridgeError("Another browser tab is connected; disconnect it first")
            db.execute("INSERT OR REPLACE INTO connection VALUES (1, ?, ?, ?)",
                       (session, mailbox, self.clock()))

    def disconnect(self, session):
        with self._connection() as db:
            db.execute("DELETE FROM connection WHERE session = ?", (session,))
            db.execute("UPDATE commands SET state = 'expired', payload = '{}' "
                       "WHERE session = ? AND state = 'queued'", (session,))
            db.execute("DELETE FROM files WHERE command_id IN "
                       "(SELECT id FROM commands WHERE state = 'expired')")

    def status(self):
        with self._connection() as db:
            row = db.execute("SELECT * FROM connection").fetchone()
            connected = bool(row and row["seen"] > self.clock() - LEASE_SECONDS)
            return {"connected": connected, "mailbox_address": row["mailbox"] if connected else "",
                    "protocol": PROTOCOL_VERSION}

    def enqueue(self, operation, mailbox, payload, files=(), timeout=120):
        if operation not in {"observe", "submit", "schedule", "cancel_schedule", "recall"}:
            raise BridgeError("Unsupported extension operation")
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > MAX_COMMAND_BYTES:
            raise BridgeError("Command exceeds the 512 KiB Native Messaging payload limit")
        if sum(len(content) for content in files) > MAX_ATTACHMENT_BYTES:
            raise BridgeError("Confirmed attachments exceed the supported 20 MiB total")
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM connection").fetchone()
            if not row or row["seen"] <= self.clock() - LEASE_SECONDS:
                raise BridgeError("Connect the 163 mailbox tab from the SmartMail extension first")
            if row["mailbox"] != mailbox:
                raise BridgeError(f"Connected Mailbox is {row['mailbox']}; intended Mailbox is {mailbox}")
            command_id = str(uuid4())
            db.execute("INSERT INTO commands VALUES (?, ?, ?, ?, ?, 'queued', NULL, ?)",
                       (command_id, row["session"], operation, encoded, self.clock() + timeout, self.clock()))
            db.executemany("INSERT INTO files VALUES (?, ?, ?)",
                           [(command_id, index, content) for index, content in enumerate(files)])
        return command_id

    def poll(self, session, ready=True):
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if not db.execute("UPDATE connection SET seen = ? WHERE session = ?",
                              (self.clock(), session)).rowcount:
                raise BridgeError("Connection was replaced or disconnected")
            db.execute("UPDATE commands SET state = 'expired', payload = '{}' "
                       "WHERE state = 'queued' AND deadline <= ?", (self.clock(),))
            db.execute("DELETE FROM files WHERE command_id IN "
                       "(SELECT id FROM commands WHERE state = 'expired')")
            if not ready:
                return None
            # One active operation per connection, even if multiple CLI processes enqueue.
            active = db.execute("SELECT 1 FROM commands WHERE session = ? "
                                "AND state IN ('claimed', 'authorized')", (session,)).fetchone()
            if active:
                return None
            row = db.execute("SELECT * FROM commands WHERE session = ? AND state = 'queued' "
                             "ORDER BY created, rowid LIMIT 1", (session,)).fetchone()
            if not row:
                return None
            db.execute("UPDATE commands SET state = 'claimed' WHERE id = ?", (row["id"],))
            return {"id": row["id"], "operation": row["operation"],
                    "deadline": row["deadline"] * 1000, "payload": json.loads(row["payload"])}

    def _active(self, db, session, command_id):
        row = db.execute("SELECT * FROM commands WHERE id = ? AND session = ?",
                         (command_id, session)).fetchone()
        if not row or row["state"] not in {"claimed", "authorized"} or row["deadline"] <= self.clock():
            raise BridgeError("Command expired, completed, or belongs to another connection")
        connection = db.execute("SELECT * FROM connection WHERE session = ?", (session,)).fetchone()
        if not connection or connection["seen"] <= self.clock() - LEASE_SECONDS:
            raise BridgeError("Extension connection expired")
        return row

    def attachment(self, session, command_id, position, offset):
        if type(position) is not int or type(offset) is not int or position < 0 or offset < 0:
            raise BridgeError("Invalid attachment position or offset")
        with self._connection() as db:
            self._active(db, session, command_id)
            row = db.execute("SELECT content FROM files WHERE command_id = ? AND position = ?",
                             (command_id, position)).fetchone()
            if not row or offset > len(row["content"]):
                raise BridgeError("Attachment not found or offset exceeds confirmed bytes")
            chunk = row["content"][offset:offset + CHUNK_BYTES]
            return {"data": base64.b64encode(chunk).decode("ascii"),
                    "next": offset + len(chunk), "done": offset + len(chunk) == len(row["content"])}

    def authorize(self, session, command_id):
        """Consume a transport permit just before the single send click.

        This does not create business Confirmation; only SmartMail can enqueue
        a confirmed submission. A permit cannot be requested twice.
        """
        with self._connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._active(db, session, command_id)
            if row["operation"] not in PERMITTED_OPERATIONS or row["state"] != "claimed":
                raise BridgeError("Operation permit is unavailable or already consumed")
            self.validate(row["operation"], json.loads(row["payload"]))
            db.execute("UPDATE commands SET state = 'authorized' WHERE id = ?", (command_id,))
            return {"permitted": True, "deadline": row["deadline"] * 1000}

    def finish(self, session, command_id, result):
        if not isinstance(result, dict):
            raise BridgeError("Extension result must be an object")
        with self._connection() as db:
            row = db.execute("SELECT * FROM commands WHERE id = ? AND session = ?",
                             (command_id, session)).fetchone()
            if not row or row["state"] not in {"claimed", "authorized", "expired"}:
                raise BridgeError("Unexpected or duplicate command result")
            outcome = result.get("outcome")
            if (row["operation"] in PERMITTED_OPERATIONS
                    and outcome in PERMITTED_OUTCOMES[row["operation"]]
                    and row["state"] != "authorized"):
                raise BridgeError(f"{outcome} result without a consumed operation permit")
            db.execute("UPDATE commands SET state = 'done', result = ?, payload = '{}' WHERE id = ?",
                       (json.dumps(result, ensure_ascii=False), command_id))
            db.execute("DELETE FROM files WHERE command_id = ?", (command_id,))

    def result(self, command_id):
        with self._connection() as db:
            row = db.execute("SELECT state, result FROM commands WHERE id = ?", (command_id,)).fetchone()
            return json.loads(row["result"]) if row and row["state"] == "done" else None

    def expire(self, command_id):
        with self._connection() as db:
            db.execute("UPDATE commands SET state = 'expired', payload = '{}' "
                       "WHERE id = ? AND state != 'done'", (command_id,))
            db.execute("DELETE FROM files WHERE command_id = ?", (command_id,))

    def exchange(self, operation, mailbox, payload, files=(), timeout=120):
        command_id = self.enqueue(operation, mailbox, payload, files, timeout)
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                result = self.result(command_id)
                if result is not None:
                    return result
                time.sleep(0.1)
            raise BridgeError("Extension command timed out; a submitted operation must be reconciled")
        finally:
            self.expire(command_id)
