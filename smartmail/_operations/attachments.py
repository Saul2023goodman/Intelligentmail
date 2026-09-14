"""Advisory attachment slots and immutable attachment snapshots."""

import hashlib
import re
from pathlib import Path, PurePosixPath
from uuid import uuid4

from ..documents import attachment_declarations
from ..errors import SmartMailError


class AttachmentOperations:
    """Advisory attachment slots and immutable attachment snapshots."""

    def suggest_attachment_slots(self, preparation_id: str) -> list[dict]:
        """Create or refresh the advisory attachment slots declared by the message body.

        Suggestions never finalize an association and never affect readiness.
        """
        preparation = self._db.execute(
            "SELECT id, body, source_id FROM preparations WHERE id = ?", (preparation_id,)).fetchone()
        if preparation is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        import_id = self._db.execute(
            "SELECT import_id FROM sources WHERE id = ?", (preparation["source_id"],)).fetchone()["import_id"]
        with self._db:
            for declared in attachment_declarations(preparation["body"]):
                label = f"Student {declared}"
                basis = f'Attachment declared in the message body: "I have attached my {declared}"'
                candidates = self._attachment_candidates(import_id, declared, preparation["source_id"])
                suggested = candidates[0]["id"] if len(candidates) == 1 else None
                existing = self._db.execute(
                    "SELECT id, suggested_source_id FROM attachment_slots WHERE preparation_id = ? AND label = ?",
                    (preparation_id, label)).fetchone()
                if existing is None:
                    self._db.execute(
                        "INSERT INTO attachment_slots VALUES (?, ?, ?, ?, ?, ?)",
                        (str(uuid4()), preparation_id, label, declared, basis, suggested))
                elif self._db.execute(
                        "SELECT 1 FROM attachments WHERE slot_id = ?", (existing["id"],)).fetchone() is None:
                    self._db.execute(
                        "UPDATE attachment_slots SET basis = ?, suggested_source_id = ? WHERE id = ?",
                        (basis, suggested, existing["id"]))
        return self.list_attachment_slots(preparation_id)

    def _attachment_candidates(self, import_id: str, declared: str, exclude_source_id: str) -> list[dict]:
        """Preserved .docx Source Materials whose filename carries the declared attachment label."""
        wanted = {token.casefold() for token in re.split(r"[^0-9A-Za-z]+", declared) if token}
        candidates = []
        for row in self._db.execute(
                "SELECT id, name, sha256 FROM sources WHERE import_id = ? ORDER BY rowid", (import_id,)):
            if row["id"] == exclude_source_id or not row["name"].casefold().endswith(".docx"):
                continue
            stem = PurePosixPath(row["name"]).name[:-5]
            tokens = {token.casefold() for token in re.split(r"[^0-9A-Za-z]+", stem) if token}
            if wanted and wanted <= tokens:
                candidates.append(dict(row))
        return candidates

    def confirm_attachment(self, preparation_id: str, slot_id: str) -> dict:
        """Confirm the slot's single suggested candidate; suggestions are never finalized automatically."""
        slot = self._db.execute(
            "SELECT * FROM attachment_slots WHERE id = ? AND preparation_id = ?",
            (slot_id, preparation_id)).fetchone()
        if slot is None:
            raise SmartMailError(f"Attachment slot not found: {slot_id}")
        if slot["suggested_source_id"] is None:
            raise SmartMailError(
                "This slot has no single suggested candidate; select a file explicitly")
        return self.set_attachment(preparation_id, slot_id, source_id=slot["suggested_source_id"])

    def set_attachment(self, preparation_id: str, slot_id: str, source_id: str | None = None,
                       path: Path | None = None) -> dict:
        """Confirm or replace a slot's file, snapshotting its bytes without conversion or merging."""
        if (source_id is None) == (path is None):
            raise SmartMailError("Provide exactly one of a preserved Source Material or a file path")
        slot = self._require_slot(preparation_id, slot_id)
        name, content, digest = self._attachment_payload(source_id, path)
        with self._db:
            self._store_attachment(preparation_id, slot, name, content, digest)
        return self.get_preparation(preparation_id)

    def add_attachment_slot(self, preparation_id: str, label: str, source_id: str | None = None,
                            path: Path | None = None) -> dict:
        """Add an operator-defined slot, optionally confirming a file at the same time."""
        label = label.strip()
        if not label:
            raise SmartMailError("An attachment slot label is required")
        if self._db.execute(
                "SELECT 1 FROM preparations WHERE id = ?", (preparation_id,)).fetchone() is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        if self._db.execute(
                "SELECT 1 FROM attachment_slots WHERE preparation_id = ? AND label = ?",
                (preparation_id, label)).fetchone():
            raise SmartMailError(f"Attachment slot already exists: {label}")
        if source_id is not None and path is not None:
            raise SmartMailError("Provide exactly one of a preserved Source Material or a file path")
        payload = self._attachment_payload(source_id, path) if (source_id or path) else None
        with self._db:
            slot = {"id": str(uuid4()), "label": label}
            self._db.execute(
                "INSERT INTO attachment_slots VALUES (?, ?, ?, ?, ?, ?)",
                (slot["id"], preparation_id, label, label,
                 f"Added by the operator: {label}", None))
            if payload is not None:
                self._store_attachment(preparation_id, slot, *payload)
        return self.get_preparation(preparation_id)

    def remove_attachment_slot(self, preparation_id: str, slot_id: str) -> dict:
        slot = self._require_slot(preparation_id, slot_id)
        with self._db:
            self._db.execute("DELETE FROM attachments WHERE slot_id = ?", (slot["id"],))
            self._db.execute("DELETE FROM attachment_slots WHERE id = ?", (slot["id"],))
        return self.get_preparation(preparation_id)

    def _require_slot(self, preparation_id: str, slot_id: str):
        slot = self._db.execute(
            "SELECT * FROM attachment_slots WHERE id = ? AND preparation_id = ?",
            (slot_id, preparation_id)).fetchone()
        if slot is None:
            raise SmartMailError(f"Attachment slot not found: {slot_id}")
        return slot

    def _attachment_payload(self, source_id: str | None, path: Path | None) -> tuple[str, bytes, str]:
        if source_id is not None:
            source = self._db.execute(
                "SELECT name, content FROM sources WHERE id = ?", (source_id,)).fetchone()
            if source is None:
                raise SmartMailError(f"Source Material not found: {source_id}")
            name, content = PurePosixPath(source["name"]).name, bytes(source["content"])
        else:
            path = Path(path)
            if not path.is_file():
                raise SmartMailError(f"Attachment file not found: {path}")
            name, content = path.name, path.read_bytes()
        return name, content, hashlib.sha256(content).hexdigest()

    def _store_attachment(self, preparation_id: str, slot: dict, name: str,
                          content: bytes, digest: str) -> None:
        prior_row = self._db.execute(
            "SELECT name, sha256 FROM attachments WHERE slot_id = ?", (slot["id"],)).fetchone()
        prior = prior_row["name"] if prior_row and prior_row["sha256"] != digest else ""
        if prior_row is None:
            self._db.execute("INSERT INTO attachments VALUES (?, ?, ?, ?, ?)",
                             (str(uuid4()), slot["id"], name, content, digest))
        else:
            self._db.execute(
                "UPDATE attachments SET name = ?, content = ?, sha256 = ? WHERE slot_id = ?",
                (name, content, digest, slot["id"]))
        if prior or prior_row is None:
            self._record_correction(preparation_id, f"attachment:{slot['label']}", name, prior)

    def read_attachment(self, attachment_id: str) -> bytes:
        row = self._db.execute("SELECT content FROM attachments WHERE id = ?", (attachment_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Attachment not found: {attachment_id}")
        return bytes(row["content"])

    def list_attachment_slots(self, preparation_id: str) -> list[dict]:
        """The Preparation's attachment slots: advisory candidates plus any confirmed file."""
        preparation = self._db.execute(
            "SELECT source_id FROM preparations WHERE id = ?", (preparation_id,)).fetchone()
        if preparation is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        import_id = self._db.execute(
            "SELECT import_id FROM sources WHERE id = ?", (preparation["source_id"],)).fetchone()["import_id"]
        slots = []
        for row in self._db.execute(
                "SELECT * FROM attachment_slots WHERE preparation_id = ? ORDER BY rowid", (preparation_id,)):
            attachment = self._db.execute(
                "SELECT id, name, sha256, length(content) AS size FROM attachments WHERE slot_id = ?",
                (row["id"],)).fetchone()
            slots.append({
                "id": row["id"], "label": row["label"], "declared": row["declared"],
                "basis": row["basis"],
                "suggested_source_id": row["suggested_source_id"],
                "candidates": self._attachment_candidates(
                    import_id, row["declared"], preparation["source_id"]),
                "attachment": dict(attachment) if attachment else None,
            })
        return slots
