"""Campaigns, Students, Outreach Tasks and preserved Source Material."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

from ..intake import read_archive_members, read_master, read_bundle
from ..identity import email_address, person_name, profile_url
from ..errors import SmartMailError


class RecordsOperations:
    """Campaigns, Students, Outreach Tasks and preserved Source Material."""

    def create_campaign(self, name: str) -> dict:
        """Create a standalone Campaign; a Student's own Campaign is established with them."""
        campaign = {"id": str(uuid4()), "name": name.strip()}
        if not campaign["name"]:
            raise SmartMailError("Campaign name is required")
        with self._db:
            self._db.execute(
                "INSERT INTO campaigns (id, name) VALUES (:id, :name)", campaign
            )
        return self.get_campaign(campaign["id"])

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
        """Register the Student, their Mailbox and their Campaign as one relationship.

        One Student owns exactly one Campaign. The link is persisted here and never
        re-derived by matching a Campaign name against a Student name.
        """
        name = name.strip()
        address = email_address(mailbox_address)
        if not name or not address:
            raise SmartMailError("Student name and a valid Mailbox address are required")
        existing = self._db.execute(
            "SELECT s.* FROM students s JOIN mailboxes m ON m.student_id = s.id WHERE m.address = ?", (address,)).fetchone()
        if existing:
            if existing["name"] != name:
                raise SmartMailError(f"Mailbox already belongs to Student {existing['id']}; select that Student or resolve ownership")
            if not self._student_campaign_id(existing["id"]):
                # A Student registered before the relationship was persisted.
                with self._db:
                    self._db.execute(
                        "INSERT INTO campaigns (id, name, student_id) VALUES (?, ?, ?)",
                        (str(uuid4()), existing["name"], existing["id"]))
            return self.get_student(existing["id"])
        student_id = str(uuid4())
        with self._db:
            self._db.execute("INSERT INTO students VALUES (?, ?)", (student_id, name))
            self._db.execute("INSERT INTO mailboxes VALUES (?, ?, ?)",
                             (str(uuid4()), student_id, address))
            self._db.execute("INSERT INTO campaigns (id, name, student_id) VALUES (?, ?, ?)",
                             (str(uuid4()), name, student_id))
        return self.get_student(student_id)

    def _student_campaign_id(self, student_id: str) -> str:
        row = self._db.execute(
            "SELECT id FROM campaigns WHERE student_id = ?", (student_id,)).fetchone()
        return row["id"] if row else ""

    def list_students(self) -> list[dict]:
        return [dict(r) for r in self._db.execute(
            "SELECT s.*, COALESCE(c.id, '') AS campaign_id FROM students s "
            "LEFT JOIN campaigns c ON c.student_id = s.id ORDER BY s.rowid")]

    def list_mailboxes(self) -> list[dict]:
        """Registered Student mailboxes with the Student's Campaign, before any intake."""
        return [dict(row) for row in self._db.execute(
            "SELECT m.id, m.student_id, m.address, s.name AS student_name, "
            "COALESCE(c.id, '') AS campaign_id FROM mailboxes m "
            "JOIN students s ON s.id = m.student_id "
            "LEFT JOIN campaigns c ON c.student_id = s.id ORDER BY m.rowid")]

    def get_student(self, student_id: str) -> dict:
        row = self._db.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Student not found: {student_id}")
        return {**dict(row), "campaign_id": self._student_campaign_id(student_id)}

    def delete_student(self, student_id: str, mailbox_address: str) -> dict:
        """Permanently remove one Student workspace and all of its local evidence.

        The mailbox address is an explicit confirmation token. Active or unknown
        external work blocks deletion because removing local evidence must never
        abandon a possibly-live mailbox operation.
        """
        student = self.get_student(student_id)
        mailbox = self._db.execute(
            "SELECT * FROM mailboxes WHERE student_id = ?", (student_id,)
        ).fetchone()
        confirmed_address = email_address(mailbox_address)
        if mailbox is None or not confirmed_address or confirmed_address != mailbox["address"]:
            raise SmartMailError("Confirm deletion with the Student's exact Mailbox address")

        unresolved = self._db.execute(
            "SELECT a.id FROM execution_attempts a "
            "JOIN tasks t ON t.id = a.task_id "
            "WHERE t.student_id = ? AND a.state IN ('in_progress', 'unknown') LIMIT 1",
            (student_id,),
        ).fetchone()
        active_schedule = self._db.execute(
            "SELECT s.id FROM external_schedules s "
            "JOIN tasks t ON t.id = s.task_id "
            "WHERE t.student_id = ? "
            "AND s.state IN ('placement_unknown', 'externally_scheduled', 'cancel_unknown') LIMIT 1",
            (student_id,),
        ).fetchone()
        if unresolved or active_schedule:
            raise SmartMailError(
                "Resolve active or unknown external mailbox work before deleting this Student")

        def ids(sql: str, parameters=()) -> list[str]:
            return [row["id"] for row in self._db.execute(sql, parameters)]

        def delete_ids(table: str, column: str, values: list[str]) -> None:
            if not values:
                return
            marks = ",".join("?" for _ in values)
            self._db.execute(f"DELETE FROM {table} WHERE {column} IN ({marks})", values)

        campaign_ids = ids("SELECT id FROM campaigns WHERE student_id = ?", (student_id,))
        if campaign_ids:
            marks = ",".join("?" for _ in campaign_ids)
            foreign_scope = self._db.execute(
                f"SELECT id FROM tasks WHERE campaign_id IN ({marks}) AND student_id != ? "
                "UNION ALL "
                f"SELECT id FROM imports WHERE campaign_id IN ({marks}) AND student_id != ? LIMIT 1",
                (*campaign_ids, student_id, *campaign_ids, student_id),
            ).fetchone()
            if foreign_scope:
                raise SmartMailError(
                    "Student Campaign contains another Student's records; repair the scope before deletion")

        task_ids = ids("SELECT id FROM tasks WHERE student_id = ?", (student_id,))
        preparation_ids = (
            ids(f"SELECT id FROM preparations WHERE task_id IN ({','.join('?' for _ in task_ids)})",
                task_ids) if task_ids else []
        )
        confirmation_ids = (
            ids(f"SELECT id FROM confirmations WHERE task_id IN ({','.join('?' for _ in task_ids)})",
                task_ids) if task_ids else []
        )
        attempt_ids = (
            ids(f"SELECT id FROM execution_attempts WHERE task_id IN ({','.join('?' for _ in task_ids)})",
                task_ids) if task_ids else []
        )
        sent_ids = (
            ids(f"SELECT id FROM sent_records WHERE task_id IN ({','.join('?' for _ in task_ids)})",
                task_ids) if task_ids else []
        )
        schedule_ids = (
            ids(f"SELECT id FROM external_schedules WHERE task_id IN ({','.join('?' for _ in task_ids)})",
                task_ids) if task_ids else []
        )
        import_ids = ids("SELECT id FROM imports WHERE student_id = ?", (student_id,))
        source_ids = (
            ids(f"SELECT id FROM sources WHERE import_id IN ({','.join('?' for _ in import_ids)})",
                import_ids) if import_ids else []
        )
        mailbox_ids = ids("SELECT id FROM mailboxes WHERE student_id = ?", (student_id,))
        observation_ids = (
            ids(f"SELECT id FROM mailbox_observation_runs WHERE mailbox_id IN ({','.join('?' for _ in mailbox_ids)})",
                mailbox_ids) if mailbox_ids else []
        )
        message_ids = (
            ids(f"SELECT id FROM mailbox_message_observations WHERE run_id IN ({','.join('?' for _ in observation_ids)})",
                observation_ids) if observation_ids else []
        )
        reconciliation_ids = (
            ids(f"SELECT id FROM reconciliations WHERE mailbox_id IN ({','.join('?' for _ in mailbox_ids)})",
                mailbox_ids) if mailbox_ids else []
        )
        plan_ids = (
            ids(f"SELECT id FROM sending_plans WHERE campaign_id IN ({','.join('?' for _ in campaign_ids)})",
                campaign_ids) if campaign_ids else []
        )
        run_ids = (
            ids(f"SELECT id FROM execution_runs WHERE campaign_id IN ({','.join('?' for _ in campaign_ids)})",
                campaign_ids) if campaign_ids else []
        )

        with self._db:
            # Break self/cross references before deleting the graph bottom-up.
            if preparation_ids:
                marks = ",".join("?" for _ in preparation_ids)
                self._db.execute(
                    f"UPDATE preparations SET superseded_by = NULL, linked_sent_record_id = NULL "
                    f"WHERE id IN ({marks})", preparation_ids)
            if sent_ids:
                marks = ",".join("?" for _ in sent_ids)
                self._db.execute(
                    f"UPDATE sent_records SET follows_sent_record_id = NULL WHERE id IN ({marks})",
                    sent_ids)
            if schedule_ids:
                marks = ",".join("?" for _ in schedule_ids)
                self._db.execute(
                    f"UPDATE external_schedules SET replaces_schedule_id = NULL WHERE id IN ({marks})",
                    schedule_ids)

            delete_ids("external_operations", "schedule_id", schedule_ids)
            delete_ids("external_operations", "confirmation_id", confirmation_ids)
            delete_ids("execution_run_items", "run_id", run_ids)
            delete_ids("execution_run_items", "attempt_id", attempt_ids)
            delete_ids("execution_run_items", "confirmation_id", confirmation_ids)
            delete_ids("sending_plan_proposals", "plan_id", plan_ids)
            delete_ids("sending_plan_proposals", "preparation_id", preparation_ids)
            delete_ids("follow_up_actions", "task_id", task_ids)
            delete_ids("reply_associations", "task_id", task_ids)
            delete_ids("reply_associations", "message_observation_id", message_ids)
            self._db.execute("DELETE FROM reply_associations WHERE student_id = ?", (student_id,))
            delete_ids("duplicate_checks", "task_id", task_ids)
            delete_ids("sent_attachments", "sent_record_id", sent_ids)
            delete_ids("external_schedules", "id", schedule_ids)
            delete_ids("sent_records", "id", sent_ids)
            delete_ids("execution_attempts", "id", attempt_ids)
            delete_ids("confirmations", "id", confirmation_ids)
            delete_ids("attachments", "slot_id", ids(
                f"SELECT id FROM attachment_slots WHERE preparation_id IN ({','.join('?' for _ in preparation_ids)})",
                preparation_ids) if preparation_ids else [])
            for table in ("attachment_slots", "transformations", "readiness_findings", "corrections"):
                delete_ids(table, "preparation_id", preparation_ids)
            delete_ids("preparations", "id", preparation_ids)
            delete_ids("exceptions", "task_id", task_ids)
            delete_ids("source_associations", "task_id", task_ids)
            delete_ids("tasks", "id", task_ids)

            delete_ids("document_findings", "source_id", source_ids)
            delete_ids("source_recognition", "source_id", source_ids)
            delete_ids("exceptions", "source_id", source_ids)
            delete_ids("source_associations", "source_id", source_ids)
            delete_ids("sources", "id", source_ids)
            delete_ids("imports", "id", import_ids)

            delete_ids("reconciliation_findings", "reconciliation_id", reconciliation_ids)
            delete_ids("reconciliation_findings", "message_observation_id", message_ids)
            delete_ids("reconciliations", "id", reconciliation_ids)
            delete_ids("mailbox_message_observations", "id", message_ids)
            delete_ids("mailbox_observation_runs", "id", observation_ids)
            delete_ids("mailbox_settings", "mailbox_id", mailbox_ids)
            delete_ids("mailboxes", "id", mailbox_ids)

            delete_ids("execution_runs", "id", run_ids)
            delete_ids("sending_plans", "id", plan_ids)
            for table in ("execution_flow", "follow_up_rules", "plan_configurations"):
                delete_ids(table, "campaign_id", campaign_ids)
            delete_ids("campaigns", "id", campaign_ids)
            self._db.execute("DELETE FROM students WHERE id = ?", (student_id,))

            # Supervisor and Institution identities are shared across Students;
            # remove only identities that became unreferenced.
            self._db.execute(
                "DELETE FROM supervisor_addresses WHERE supervisor_id IN "
                "(SELECT s.id FROM supervisors s LEFT JOIN tasks t ON t.supervisor_id = s.id "
                "WHERE t.id IS NULL)")
            self._db.execute(
                "DELETE FROM supervisors WHERE NOT EXISTS "
                "(SELECT 1 FROM tasks t WHERE t.supervisor_id = supervisors.id)")
            self._db.execute(
                "DELETE FROM institutions WHERE NOT EXISTS "
                "(SELECT 1 FROM supervisors s WHERE s.institution_id = institutions.id)")

        return {
            "id": student["id"], "name": student["name"],
            "mailbox": mailbox["address"], "campaign_ids": campaign_ids, "deleted": True,
        }

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

    def import_source_set(self, campaign_id: str, student_id: str,
                          path: Path, master_name: str | None = None) -> dict:
        """Import a flattened source set whose supervisor master list is optional.

        Zero-master imports preserve every member and create no Tasks here;
        draft letters then establish their own Tasks in
        :meth:`prepare_from_documents`.  With one master the familiar
        row-based Task import runs.  More than one workbook requires an
        explicit choice (the review flow sends one member name).
        """
        self.get_campaign(campaign_id)
        self.get_student(student_id)
        suffix = Path(path).suffix.lower()
        data = path.read_bytes()
        try:
            if suffix == ".xlsx":
                members = [(path.name, data)]
            elif suffix == ".zip":
                members = read_archive_members(data)
            else:
                raise SmartMailError("Supported inputs are .xlsx workbooks or .zip bundles")
        except (ValueError, OSError, KeyError, BadZipFile, ParseError) as error:
            raise SmartMailError(f"Cannot import Source Material: {error}") from error
        if not members:
            raise SmartMailError("The archive contains no supported .docx, .xlsx or .csv members")

        workbook_indexes = [index for index, (name, _) in enumerate(members)
                            if name.lower().endswith(".xlsx")]
        if master_name:
            master_index = next((index for index, (name, _) in enumerate(members)
                                 if name == master_name), None)
            if master_index is None:
                raise SmartMailError(f"Selected master workbook is not in the source set: {master_name}")
        elif master_name is None:
            # No explicit UI decision: a unique workbook is treated as master.
            if len(workbook_indexes) == 1:
                master_index = workbook_indexes[0]
            elif not workbook_indexes:
                master_index = None
            else:
                raise SmartMailError(
                    "The source set contains more than one .xlsx workbook; revise or "
                    "exclude the workbooks that are not supervisor master lists")
        else:
            # Empty string is the UI's explicit "no master in this set" decision.
            master_index = None

        rows = read_master(members[master_index][1]) if master_index is not None else []
        known_sources = {
            row["sha256"]: dict(row) for row in self._db.execute(
                "SELECT s.id, s.name, s.sha256, s.import_id FROM sources s "
                "JOIN imports i ON i.id = s.import_id "
                "WHERE i.campaign_id = ? AND i.student_id = ?", (campaign_id, student_id))}
        resolved_sources = []
        reused_sources = []
        for name, member_data in members:
            sha = hashlib.sha256(member_data).hexdigest()
            known = known_sources.get(sha)
            if known is not None:
                resolved_sources.append((known["id"], True))
                reused_sources.append({"id": known["id"], "name": name, "sha256": sha})
            else:
                resolved_sources.append((str(uuid4()), False))

        import_id = str(uuid4())
        master_source_id = resolved_sources[master_index][0] if master_index is not None else ""
        master_sha = hashlib.sha256(members[master_index][1]).hexdigest() if master_index is not None else ""
        row_results = []
        task_ids = []
        seen_tasks: dict[str, tuple] = {}
        with self._db:
            self._db.execute("INSERT INTO imports VALUES (?, ?, ?)", (import_id, campaign_id, student_id))
            for (source_id, reused), (name, member_data) in zip(resolved_sources, members):
                if not reused:
                    self._db.execute("INSERT INTO sources VALUES (?, ?, ?, ?, ?)",
                                     (source_id, import_id, name, member_data,
                                      hashlib.sha256(member_data).hexdigest()))
            if master_index is not None:
                for row in rows:
                    result = self._import_master_row(
                        row, campaign_id, student_id, master_source_id, master_sha,
                        set(), seen_tasks, False)
                    row_results.append(result)
                    if result["task_id"] not in task_ids:
                        task_ids.append(result["task_id"])
        return {
            "id": import_id,
            "task_ids": task_ids,
            "duplicate": False,
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

    def ensure_task_from_correspondent(self, campaign_id: str, student_id: str,
                                       source_id: str, institution_name: str,
                                       supervisor_name: str, address: str,
                                       letter_index: int = 1) -> dict | None:
        """Create (or reuse) the Outreach Task a draft letter addresses.

        Used only for master-less imports: the letter itself is the identity
        record.  Missing recipient addresses follow the same blocking rule as
        master rows.  An empty institution is allowed and left unresolved.
        """
        institution_name = (institution_name or "").strip()
        supervisor_name = (supervisor_name or "").strip()
        if not supervisor_name:
            return None
        address = email_address(address)
        profile = ""
        institution = self._db.execute(
            "SELECT id FROM institutions WHERE name = ?", (institution_name,)).fetchone()
        institution_id = institution["id"] if institution else str(uuid4())
        if institution is None:
            self._db.execute("INSERT INTO institutions VALUES (?, ?)",
                             (institution_id, institution_name))
        candidates = list(self._db.execute(
            "SELECT DISTINCT s.* FROM supervisors s LEFT JOIN supervisor_addresses a ON a.supervisor_id = s.id "
            "WHERE s.institution_id = ? AND ((s.profile = ? AND s.profile != '') OR a.address = ?)",
            (institution_id, profile, address)))
        matches = [candidate for candidate in candidates
                   if person_name(candidate["name"]) == person_name(supervisor_name)
                   and not (profile and candidate["profile"] and profile != candidate["profile"])]
        supervisor_id = matches[0]["id"] if matches else str(uuid4())
        if len(matches) != 1:
            self._db.execute("INSERT INTO supervisors VALUES (?, ?, ?, ?)",
                             (supervisor_id, supervisor_name, institution_id, profile))
        if address:
            self._db.execute("INSERT OR IGNORE INTO supervisor_addresses VALUES (?, ?)",
                             (supervisor_id, address))
        existing = self._db.execute(
            "SELECT id FROM tasks WHERE student_id = ? AND supervisor_id = ? AND campaign_id = ?",
            (student_id, supervisor_id, campaign_id)).fetchone()
        task_id = existing["id"] if existing else str(uuid4())
        created = existing is None
        if created:
            self._db.execute("INSERT INTO tasks VALUES (?, ?, ?, ?)",
                             (task_id, student_id, supervisor_id, campaign_id))
        if not address:
            self._record_task_exception(
                task_id, source_id, "invalid_recipient",
                f"Letter {letter_index}: no usable recipient address is recorded",
                blocking=1)
        for candidate in self._db.execute("SELECT * FROM supervisors WHERE id != ?", (supervisor_id,)).fetchall():
            shared_address = address and self._db.execute(
                "SELECT 1 FROM supervisor_addresses WHERE supervisor_id = ? AND address = ?",
                (candidate["id"], address)).fetchone()
            if (shared_address or (candidate["institution_id"] == institution_id
                                   and institution_name
                                   and person_name(candidate["name"]) == person_name(supervisor_name))):
                detail = ("Unresolved Supervisor identity; candidates: "
                          + ", ".join([supervisor_id, candidate["id"]]))
                for affected in (supervisor_id, candidate["id"]):
                    for affected_task in self._db.execute(
                            "SELECT id FROM tasks WHERE supervisor_id = ?", (affected,)).fetchall():
                        self._record_task_exception(
                            affected_task["id"], source_id, "identity_ambiguity", detail, blocking=1)
        evidence = {
            "source": self._db.execute("SELECT name FROM sources WHERE id = ?", (source_id,)).fetchone()["name"],
            "institution": institution_name, "supervisor": supervisor_name,
            "recipient": address or "", "letter_index": letter_index,
        }
        self._db.execute("INSERT OR IGNORE INTO source_associations VALUES (?, ?, ?, ?, ?)",
                         (task_id, source_id, "document", letter_index,
                          json.dumps(evidence, ensure_ascii=False, default=str)))
        self._record_prior_outreach_conflict(task_id, source_id)
        return {"task_id": task_id, "supervisor_id": supervisor_id, "created": created,
                "institution_name": institution_name, "supervisor_name": supervisor_name}

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
