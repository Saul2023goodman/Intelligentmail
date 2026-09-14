"""Campaigns, Students, Outreach Tasks and preserved Source Material."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

from ..intake import read_master, read_bundle
from ..identity import email_address, person_name, profile_url
from ..errors import SmartMailError


class RecordsOperations:
    """Campaigns, Students, Outreach Tasks and preserved Source Material."""

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

    def confirm_task_identity(self, task_id: str) -> dict:
        """Explicitly confirm a Task's recorded Supervisor identity, clearing its ambiguity Blocker."""
        if self._db.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is None:
            raise SmartMailError(f"Outreach Task not found: {task_id}")
        ambiguous = list(self._db.execute(
            "SELECT id FROM exceptions WHERE task_id = ? AND code = 'identity_ambiguity'", (task_id,)))
        if not ambiguous:
            raise SmartMailError(
                f"Outreach Task has no unresolved Supervisor identity ambiguity: {task_id}")
        with self._db:
            self._db.execute(
                "DELETE FROM exceptions WHERE task_id = ? AND code = 'identity_ambiguity'", (task_id,))
            for preparation in self._db.execute(
                    "SELECT id FROM preparations WHERE task_id = ?", (task_id,)):
                self._revalidate(preparation["id"])
        return self.get_task(task_id)

    def list_exceptions(self, campaign_id: str) -> list[dict]:
        """Blocking and non-blocking Exceptions with their source evidence and readiness findings."""
        self.get_campaign(campaign_id)
        return [self._exception_view(row) for row in self._db.execute(
            "SELECT e.*, s.name AS supervisor_name FROM exceptions e "
            "JOIN tasks t ON t.id = e.task_id JOIN supervisors s ON s.id = t.supervisor_id "
            "WHERE t.campaign_id = ? ORDER BY e.rowid", (campaign_id,))]

    def get_exception(self, exception_id: str) -> dict:
        row = self._db.execute(
            "SELECT e.*, s.name AS supervisor_name FROM exceptions e "
            "JOIN tasks t ON t.id = e.task_id JOIN supervisors s ON s.id = t.supervisor_id "
            "WHERE e.id = ?", (exception_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Exception not found: {exception_id}")
        return self._exception_view(row)

    def _exception_view(self, row) -> dict:
        source = self._db.execute(
            "SELECT id, name, sha256 FROM sources WHERE id = ?", (row["source_id"],)).fetchone()
        task = self._db.execute("SELECT student_id FROM tasks WHERE id = ?", (row["task_id"],)).fetchone()
        return {
            "id": row["id"], "code": row["code"], "detail": row["detail"],
            "blocking": bool(row["blocking"]), "task_id": row["task_id"],
            "student_id": task["student_id"], "supervisor_name": row["supervisor_name"],
            "source": dict(source) if source else None,
            "preparation_ids": [r["id"] for r in self._db.execute(
                "SELECT id FROM preparations WHERE task_id = ? AND superseded_by IS NULL ORDER BY rowid",
                (row["task_id"],))],
            "readiness_findings": [dict(r) for r in self._db.execute(
                "SELECT code, detail, blocking FROM readiness_findings WHERE preparation_id IN "
                "(SELECT id FROM preparations WHERE task_id = ? AND superseded_by IS NULL) ORDER BY rowid",
                (row["task_id"],))],
        }

    def _campaign_of_task(self, task_id: str) -> str:
        row = self._db.execute(
            "SELECT campaign_id FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Outreach Task not found: {task_id}")
        return row["campaign_id"]
