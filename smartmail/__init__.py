"""SmartMail's persistent command/query boundary for local outreach operations."""

import sqlite3
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

from .intake import read_master, read_bundle
from .identity import email_address, person_name, profile_url


class SmartMailError(ValueError):
    """An operator-visible command or query error."""


class SmartMail:
    def __init__(self, home: Path):
        self.home = Path(home).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.home / "smartmail.sqlite3")
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS campaigns (id TEXT PRIMARY KEY, name TEXT NOT NULL)"
        )
        self._db.commit()
        self._db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._db.close()

    def create_campaign(self, name: str) -> dict:
        campaign = {"id": str(uuid4()), "name": name.strip()}
        if not campaign["name"]:
            raise SmartMailError("Campaign name is required")
        with self._db:
            self._db.execute(
                "INSERT INTO campaigns VALUES (:id, :name)", campaign
            )
        return campaign

    def list_campaigns(self) -> list[dict]:
        return [dict(row) for row in self._db.execute("SELECT * FROM campaigns ORDER BY rowid")]

    def get_campaign(self, campaign_id: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM campaigns WHERE id = ?", (campaign_id,)
        ).fetchone()
        if row is None:
            raise SmartMailError(f"Campaign not found: {campaign_id}")
        return dict(row)

    def create_student(self, name: str, mailbox_address: str) -> dict:
        name = name.strip()
        address = email_address(mailbox_address)
        if not name or not address:
            raise SmartMailError("Student name and a valid Mailbox address are required")
        existing = self._db.execute(
            "SELECT s.* FROM students s JOIN mailboxes m ON m.student_id = s.id WHERE m.address = ?", (address,)).fetchone()
        if existing:
            if existing["name"] != name:
                raise SmartMailError(f"Mailbox already belongs to Student {existing['id']}; select that Student or resolve ownership")
            return dict(existing)
        student_id = str(uuid4())
        with self._db:
            self._db.execute("INSERT INTO students VALUES (?, ?)", (student_id, name.strip()))
            self._db.execute("INSERT INTO mailboxes VALUES (?, ?, ?)",
                             (str(uuid4()), student_id, address))
        return self.get_student(student_id)

    def list_students(self) -> list[dict]:
        return [dict(r) for r in self._db.execute("SELECT * FROM students ORDER BY rowid")]

    def get_student(self, student_id: str) -> dict:
        row = self._db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Student not found: {student_id}")
        return dict(row)

    def import_master(self, campaign_id: str, student_id: str, path: Path) -> dict:
        self.get_campaign(campaign_id)
        self.get_student(student_id)
        try:
            sources, master_index = read_bundle(Path(path))
            rows = read_master(sources[master_index][1])
        except (ValueError, OSError, KeyError, BadZipFile, ParseError) as error:
            raise SmartMailError(f"Cannot import Source Material: {error}") from error
        import_id = str(uuid4())
        source_ids = [str(uuid4()) for _ in sources]
        source_id = source_ids[master_index]
        task_ids = []
        with self._db:
            self._db.execute("INSERT INTO imports VALUES (?, ?, ?)", (import_id, campaign_id, student_id))
            for sid, (name, data) in zip(source_ids, sources):
                self._db.execute("INSERT INTO sources VALUES (?, ?, ?, ?, ?)",
                                 (sid, import_id, name, data, hashlib.sha256(data).hexdigest()))
            for row in rows:
                values = row["values"]
                institution = self._db.execute("SELECT id FROM institutions WHERE name = ?",
                                               (values["institution"],)).fetchone()
                institution_id = institution["id"] if institution else str(uuid4())
                if institution is None:
                    self._db.execute("INSERT INTO institutions VALUES (?, ?)", (institution_id, values["institution"]))
                address = email_address(values["address"])
                profile = profile_url(values["profile"])
                candidates = list(self._db.execute(
                    "SELECT DISTINCT s.* FROM supervisors s LEFT JOIN supervisor_addresses a ON a.supervisor_id = s.id "
                    "WHERE s.institution_id = ? AND ((s.profile = ? AND s.profile != '') OR a.address = ?)",
                    (institution_id, profile, address)))
                matches = [s for s in candidates if person_name(s["name"]) == person_name(values["name"])
                           and not (profile and s["profile"] and profile != s["profile"])]
                prior_row = list(self._db.execute(
                    "SELECT DISTINCT s.* FROM supervisors s JOIN tasks t ON t.supervisor_id = s.id "
                    "JOIN source_associations a ON a.task_id = t.id JOIN sources m ON m.id = a.source_id "
                    "WHERE m.sha256 = ? AND a.sheet = ? AND a.row = ?",
                    (hashlib.sha256(sources[master_index][1]).hexdigest(), row["sheet"], row["row"])))
                if len(prior_row) == 1:
                    matches = prior_row
                supervisor_id = matches[0]["id"] if len(matches) == 1 else str(uuid4())
                if len(matches) != 1:
                    self._db.execute("INSERT INTO supervisors VALUES (?, ?, ?, ?)",
                                     (supervisor_id, values["name"], institution_id, profile))
                elif profile and not matches[0]["profile"]:
                    self._db.execute("UPDATE supervisors SET profile = ? WHERE id = ?", (profile, supervisor_id))
                if address:
                    self._db.execute("INSERT OR IGNORE INTO supervisor_addresses VALUES (?, ?)", (supervisor_id, address))
                existing = self._db.execute("SELECT id FROM tasks WHERE student_id = ? AND supervisor_id = ? AND campaign_id = ?",
                                            (student_id, supervisor_id, campaign_id)).fetchone()
                task_id = existing["id"] if existing else str(uuid4())
                if not existing:
                    self._db.execute("INSERT INTO tasks VALUES (?, ?, ?, ?)",
                                     (task_id, student_id, supervisor_id, campaign_id))
                ambiguous = []
                for s in self._db.execute("SELECT * FROM supervisors WHERE id != ?", (supervisor_id,)).fetchall():
                    shared_address = address and self._db.execute(
                        "SELECT 1 FROM supervisor_addresses WHERE supervisor_id = ? AND address = ?", (s["id"], address)).fetchone()
                    if (shared_address or (profile and s["profile"] == profile)
                            or (s["institution_id"] == institution_id and person_name(s["name"]) == person_name(values["name"]))):
                        ambiguous.append(s["id"])
                if ambiguous:
                    affected = [supervisor_id, *ambiguous]
                    detail = "Unresolved Supervisor identity; candidates: " + ", ".join(affected)
                    for candidate in affected:
                        for affected_task in self._db.execute("SELECT id FROM tasks WHERE supervisor_id = ?", (candidate,)).fetchall():
                            self._db.execute("INSERT INTO exceptions VALUES (?, ?, ?, ?, ?, 1)",
                                             (str(uuid4()), affected_task["id"], source_id, "identity_ambiguity", detail))
                if not address:
                    self._db.execute("INSERT INTO exceptions VALUES (?, ?, ?, ?, ?, 1)",
                                     (str(uuid4()), task_id, source_id, "invalid_recipient",
                                      f"{row['sheet']}!{row['row']}: Email is missing or unsupported: {values['address']}"))
                self._db.execute("INSERT INTO source_associations VALUES (?, ?, ?, ?, ?)",
                                 (task_id, source_id, row["sheet"], row["row"], json.dumps(row["evidence"], ensure_ascii=False, default=str)))
                if task_id not in task_ids:
                    task_ids.append(task_id)
        return {"id": import_id, "task_ids": task_ids}

    def get_import(self, import_id: str) -> dict:
        row = self._db.execute("SELECT * FROM imports WHERE id = ?", (import_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Import not found: {import_id}")
        return {**dict(row), "sources": [dict(r) for r in self._db.execute(
            "SELECT id, name, sha256, length(content) AS size FROM sources WHERE import_id = ? ORDER BY rowid", (import_id,))]}

    def list_imports(self, campaign_id: str) -> list[dict]:
        self.get_campaign(campaign_id)
        return [dict(r) for r in self._db.execute("SELECT * FROM imports WHERE campaign_id = ? ORDER BY rowid", (campaign_id,))]

    def read_source(self, source_id: str) -> bytes:
        row = self._db.execute("SELECT content FROM sources WHERE id = ?", (source_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Source Material not found: {source_id}")
        return bytes(row["content"])

    def materialize_source(self, source_id: str) -> Path:
        content = self.read_source(source_id)
        name = self._db.execute("SELECT name FROM sources WHERE id = ?", (source_id,)).fetchone()[0]
        destination = self.home / "opened" / str(uuid4()) / Path(name).name
        destination.parent.mkdir(parents=True)
        destination.write_bytes(content)
        return destination

    def list_tasks(self, campaign_id: str) -> list[dict]:
        self.get_campaign(campaign_id)
        return [dict(row) for row in self._db.execute(
            "SELECT t.*, st.name AS student_name, s.name AS supervisor_name, i.name AS institution_name, "
            "(SELECT count(*) FROM exceptions e WHERE e.task_id = t.id) AS exception_count "
            "FROM tasks t JOIN students st ON st.id = t.student_id JOIN supervisors s ON s.id = t.supervisor_id "
            "JOIN institutions i ON i.id = s.institution_id WHERE t.campaign_id = ? ORDER BY t.rowid", (campaign_id,))]

    def get_task(self, task_id: str) -> dict:
        row = self._db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Outreach Task not found: {task_id}")
        task = dict(row)
        task["student"] = self.get_student(task["student_id"])
        task["campaign"] = self.get_campaign(task["campaign_id"])
        task["mailbox"] = dict(self._db.execute("SELECT * FROM mailboxes WHERE student_id = ?", (task["student_id"],)).fetchone())
        supervisor = dict(self._db.execute("SELECT * FROM supervisors WHERE id = ?", (task["supervisor_id"],)).fetchone())
        supervisor["addresses"] = [r[0] for r in self._db.execute("SELECT address FROM supervisor_addresses WHERE supervisor_id = ? ORDER BY address", (supervisor["id"],))]
        task["supervisor"] = supervisor
        task["institution"] = dict(self._db.execute("SELECT * FROM institutions WHERE id = ?", (supervisor["institution_id"],)).fetchone())
        task["source_associations"] = [
            {**dict(r), "evidence": json.loads(r["evidence"])} for r in self._db.execute(
                "SELECT source_id, sheet, row, evidence FROM source_associations WHERE task_id = ? ORDER BY rowid", (task_id,))
        ]
        task["exceptions"] = [dict(r) for r in self._db.execute("SELECT * FROM exceptions WHERE task_id = ? ORDER BY rowid", (task_id,))]
        return task
