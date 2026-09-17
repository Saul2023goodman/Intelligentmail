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

    def list_mailboxes(self) -> list[dict]:
        """Registered Student mailboxes, available before any Campaign intake."""
        return [dict(row) for row in self._db.execute(
            "SELECT m.id, m.student_id, m.address, s.name AS student_name "
            "FROM mailboxes m JOIN students s ON s.id = m.student_id ORDER BY m.rowid")]

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
        master_data = sources[master_index][1]
        master_sha = hashlib.sha256(master_data).hexdigest()
        known_sources = {
            row["sha256"]: dict(row) for row in self._db.execute(
                "SELECT s.id, s.name, s.sha256, s.import_id FROM sources s "
                "JOIN imports i ON i.id = s.import_id "
                "WHERE i.campaign_id = ? AND i.student_id = ?", (campaign_id, student_id))}
        prior_master = known_sources.get(master_sha)
        prior_keys: set[tuple] = set()
        if prior_master is not None:
            prior_keys = {
                (found["sheet"], found["row"]) for found in self._db.execute(
                    "SELECT sheet, row FROM source_associations WHERE source_id = ?",
                    (prior_master["id"],))}
        resolved_sources = []
        reused_sources = []
        for name, data in sources:
            sha = hashlib.sha256(data).hexdigest()
            known = known_sources.get(sha)
            if known is not None:
                resolved_sources.append((known["id"], True))
                reused_sources.append({"id": known["id"], "name": name, "sha256": sha})
            else:
                resolved_sources.append((str(uuid4()), False))
        duplicate_import = (
            prior_master is not None and bool(prior_keys)
            and all(reused for _, reused in resolved_sources)
            and all((row["sheet"], row["row"]) in prior_keys for row in rows))
        import_id = prior_master["import_id"] if duplicate_import else str(uuid4())
        master_source_id = resolved_sources[master_index][0]
        row_results = []
        task_ids = []
        seen_tasks: dict[str, tuple] = {}
        with self._db:
            if not duplicate_import:
                self._db.execute("INSERT INTO imports VALUES (?, ?, ?)", (import_id, campaign_id, student_id))
                for (source_id, reused), (name, data) in zip(resolved_sources, sources):
                    if not reused:
                        self._db.execute("INSERT INTO sources VALUES (?, ?, ?, ?, ?)",
                                         (source_id, import_id, name, data,
                                          hashlib.sha256(data).hexdigest()))
            for row in rows:
                result = self._import_master_row(
                    row, campaign_id, student_id, master_source_id, master_sha,
                    prior_keys, seen_tasks, duplicate_import)
                row_results.append(result)
                if result["task_id"] not in task_ids:
                    task_ids.append(result["task_id"])
        return {
            "id": import_id,
            "task_ids": task_ids,
            "duplicate": duplicate_import,
            "reused_sources": reused_sources,
            "rows": row_results,
            "summary": {
                "rows": len(row_results),
                "new": sum(1 for result in row_results if result["outcome"] == "new"),
                "reused": sum(1 for result in row_results if result["outcome"] == "reused"),
                "duplicate": sum(1 for result in row_results if result["outcome"] == "duplicate"),
                "conflicts": sum(1 for result in row_results if result["conflict"]),
                "new_sources": sum(1 for _, reused in resolved_sources if not reused),
            },
        }

    def _import_master_row(self, row: dict, campaign_id: str, student_id: str,
                           source_id: str, master_sha: str, prior_keys: set[tuple],
                           seen_tasks: dict[str, tuple], duplicate_import: bool) -> dict:
        values = row["values"]
        sheet, number = row["sheet"], row["row"]
        result = {
            "sheet": sheet, "row": number, "task_id": "", "supervisor_id": "",
            "outcome": "new", "changes": [], "conflict": False,
        }
        if duplicate_import and (sheet, number) in prior_keys:
            prior = self._db.execute(
                "SELECT DISTINCT t.id AS task_id, t.supervisor_id "
                "FROM supervisors s JOIN tasks t ON t.supervisor_id = s.id "
                "JOIN source_associations a ON a.task_id = t.id JOIN sources m ON m.id = a.source_id "
                "JOIN imports i ON i.id = m.import_id "
                "WHERE m.sha256 = ? AND i.campaign_id = ? AND i.student_id = ? "
                "AND a.sheet = ? AND a.row = ?",
                (master_sha, campaign_id, student_id, sheet, number)).fetchall()
            task_id = prior[0]["task_id"]
            result.update(task_id=task_id, supervisor_id=prior[0]["supervisor_id"],
                          outcome="reused")
            result["conflict"] = self._record_prior_outreach_conflict(task_id, source_id)
            return result
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
        # Source-record continuity is global: the exact workbook bytes, worksheet
        # and row reuse the recorded Supervisor across Students and Campaigns,
        # even while the row itself remains unresolved.
        prior_row = list(self._db.execute(
            "SELECT DISTINCT s.* FROM supervisors s JOIN tasks t ON t.supervisor_id = s.id "
            "JOIN source_associations a ON a.task_id = t.id JOIN sources m ON m.id = a.source_id "
            "WHERE m.sha256 = ? AND a.sheet = ? AND a.row = ?",
            (master_sha, sheet, number)))
        if len(prior_row) == 1:
            matches = prior_row
        supervisor_created = len(matches) != 1
        profile_added = False
        supervisor_id = matches[0]["id"] if matches else str(uuid4())
        if supervisor_created:
            self._db.execute("INSERT INTO supervisors VALUES (?, ?, ?, ?)",
                             (supervisor_id, values["name"], institution_id, profile))
        elif profile and not matches[0]["profile"]:
            self._db.execute("UPDATE supervisors SET profile = ? WHERE id = ?", (profile, supervisor_id))
            profile_added = True
        address_added = False
        if address:
            already_known = self._db.execute(
                "SELECT 1 FROM supervisor_addresses WHERE supervisor_id = ? AND address = ?",
                (supervisor_id, address)).fetchone()
            self._db.execute("INSERT OR IGNORE INTO supervisor_addresses VALUES (?, ?)",
                             (supervisor_id, address))
            address_added = already_known is None and not supervisor_created
        if address_added:
            result["changes"].append({
                "code": "address_added",
                "detail": f"{sheet}!{number}: added recorded Supervisor address {address}",
            })
        if profile_added:
            result["changes"].append({
                "code": "profile_added",
                "detail": f"{sheet}!{number}: retained later reliable Supervisor profile {profile}",
            })
        existing = self._db.execute("SELECT id FROM tasks WHERE student_id = ? AND supervisor_id = ? AND campaign_id = ?",
                                    (student_id, supervisor_id, campaign_id)).fetchone()
        task_created = existing is None
        task_id = existing["id"] if existing else str(uuid4())
        if task_created:
            self._db.execute("INSERT INTO tasks VALUES (?, ?, ?, ?)",
                             (task_id, student_id, supervisor_id, campaign_id))
        first_seen = seen_tasks.get(task_id)
        duplicate_row = (
            first_seen is not None and not task_created
            and not address_added and not profile_added)
        if task_created:
            outcome = "new"
        elif duplicate_row:
            outcome = "duplicate"
        else:
            outcome = "reused"
        result["outcome"] = outcome
        seen_tasks.setdefault(task_id, (sheet, number))
        ambiguous = []
        for candidate in self._db.execute("SELECT * FROM supervisors WHERE id != ?", (supervisor_id,)).fetchall():
            shared_address = address and self._db.execute(
                "SELECT 1 FROM supervisor_addresses WHERE supervisor_id = ? AND address = ?", (candidate["id"], address)).fetchone()
            if (shared_address or (profile and candidate["profile"] == profile)
                    or (candidate["institution_id"] == institution_id
                        and person_name(candidate["name"]) == person_name(values["name"]))):
                ambiguous.append(candidate["id"])
        if ambiguous:
            affected = [supervisor_id, *ambiguous]
            detail = "Unresolved Supervisor identity; candidates: " + ", ".join(affected)
            for candidate_id in affected:
                for affected_task in self._db.execute("SELECT id FROM tasks WHERE supervisor_id = ?", (candidate_id,)).fetchall():
                    self._record_task_exception(
                        affected_task["id"], source_id, "identity_ambiguity", detail, blocking=1)
        if duplicate_row:
            first_sheet, first_row = first_seen
            self._record_task_exception(
                task_id, source_id, "duplicate_import_row",
                f"{sheet}!{number}: the same Supervisor already appears at "
                f"{first_sheet}!{first_row}; one Outreach Task is retained", blocking=0)
        if not address:
            recorded = [found[0] for found in self._db.execute(
                "SELECT address FROM supervisor_addresses WHERE supervisor_id = ? ORDER BY address",
                (supervisor_id,))]
            if recorded:
                result["changes"].append({
                    "code": "address_absent_in_row",
                    "detail": f"{sheet}!{number}: no usable address in this row; recorded "
                              f"address(es) retained: {', '.join(recorded)}",
                })
            else:
                self._record_task_exception(
                    task_id, source_id, "invalid_recipient",
                    f"{sheet}!{number}: Email is missing or unsupported: {values['address']}",
                    blocking=1)
        self._db.execute("INSERT OR IGNORE INTO source_associations VALUES (?, ?, ?, ?, ?)",
                         (task_id, source_id, sheet, number,
                          json.dumps(row["evidence"], ensure_ascii=False, default=str)))
        result["task_id"] = task_id
        result["supervisor_id"] = supervisor_id
        result["conflict"] = self._record_prior_outreach_conflict(task_id, source_id)
        return result

    def _record_task_exception(self, task_id: str, source_id: str, code: str,
                               detail: str, blocking: int = 1) -> bool:
        """Record a task Exception once per condition; repeat imports never duplicate it."""
        if self._db.execute(
                "SELECT 1 FROM exceptions WHERE task_id = ? AND code = ? AND detail = ?",
                (task_id, code, detail)).fetchone():
            return False
        self._db.execute(
            "INSERT INTO exceptions VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid4()), task_id, source_id, code, detail, 1 if blocking else 0))
        return True

    def _record_prior_outreach_conflict(self, task_id: str, source_id: str) -> bool:
        """Block a task whose Student already sent initial outreach to its Supervisor.

        Evidence is the Campaign's immutable Sent Records followed by the Student's
        own outbound Mailbox observations, matching the ticket 07 duplicate rules.
        The exception is recorded once and resolved explicitly by the operator.
        """
        if self._db.execute(
                "SELECT 1 FROM exceptions WHERE task_id = ? AND code = 'prior_outreach_conflict'",
                (task_id,)).fetchone():
            return True
        basis, detail = self._prior_outreach_evidence(task_id)
        if basis is None:
            return False
        self._db.execute(
            "INSERT INTO exceptions VALUES (?, ?, ?, ?, ?, 1)",
            (str(uuid4()), task_id, source_id, "prior_outreach_conflict", detail))
        return True

    def _prior_outreach_evidence(self, task_id: str) -> tuple[str | None, str]:
        task = self._db.execute(
            "SELECT student_id, supervisor_id, campaign_id FROM tasks WHERE id = ?",
            (task_id,)).fetchone()
        if task is None:
            return None, ""
        sent = self._db.execute(
            "SELECT sr.id, sr.content FROM sent_records sr JOIN tasks t ON t.id = sr.task_id "
            "WHERE t.student_id = ? AND t.supervisor_id = ? AND t.campaign_id = ? "
            "AND sr.action_kind = 'initial' ORDER BY sr.rowid LIMIT 1",
            (task["student_id"], task["supervisor_id"], task["campaign_id"])).fetchone()
        if sent is not None:
            recipient = json.loads(sent["content"]).get("recipient", "")
            return "sent_record", (
                "Initial outreach was already Sent for this Student and Supervisor in this "
                f"Campaign: Sent Record {sent['id']} to {recipient}. Repeated initial outreach "
                "requires operator resolution")
        if self._db.execute(
                "SELECT 1 FROM exceptions WHERE task_id = ? AND code = 'identity_ambiguity' "
                "AND blocking = 1", (task_id,)).fetchone():
            return None, ""
        addresses = {row[0].casefold() for row in self._db.execute(
            "SELECT address FROM supervisor_addresses WHERE supervisor_id = ?",
            (task["supervisor_id"],))}
        for observation in self._db.execute(
                "SELECT o.counterpart, o.subject FROM mailbox_message_observations o "
                "JOIN mailbox_observation_runs r ON r.id = o.run_id "
                "JOIN mailboxes m ON m.id = r.mailbox_id "
                "WHERE m.student_id = ? AND o.direction = 'outbound' AND o.status = 'sent' "
                "AND o.ambiguity = '' ORDER BY o.rowid", (task["student_id"],)):
            recipient = email_address(observation["counterpart"])
            if recipient and recipient.casefold() in addresses:
                return "mailbox_observation", (
                    f"The Student's Mailbox already records an outbound sent message to "
                    f"{recipient} (subject: {observation['subject']}). Repeated initial "
                    "outreach requires operator resolution")
        return None, ""

    def resolve_prior_outreach(self, task_id: str) -> dict:
        """Record the operator's resolution of import-time prior-outreach evidence."""
        if self._db.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone() is None:
            raise SmartMailError(f"Outreach Task not found: {task_id}")
        unresolved = list(self._db.execute(
            "SELECT id FROM exceptions WHERE task_id = ? AND code = 'prior_outreach_conflict'",
            (task_id,)))
        if not unresolved:
            raise SmartMailError(
                f"Outreach Task has no unresolved prior-outreach conflict: {task_id}")
        with self._db:
            self._db.execute(
                "DELETE FROM exceptions WHERE task_id = ? AND code = 'prior_outreach_conflict'",
                (task_id,))
            for preparation in self._db.execute(
                    "SELECT id FROM preparations WHERE task_id = ?", (task_id,)):
                self._revalidate(preparation["id"])
        return self.get_task(task_id)

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
