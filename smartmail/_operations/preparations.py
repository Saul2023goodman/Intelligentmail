"""Document association, Preparation, readiness corrections and Rewrite history."""

import json
from uuid import uuid4

from ..documents import DocumentError, association_key, parse_draft, read_paragraphs
from ..identity import email_address, person_name
from ..errors import SmartMailError


class PreparationOperations:
    """Document association, Preparation, readiness corrections and Rewrite history."""

    def prepare_from_documents(self, import_id: str) -> dict:
        """Associate supported draft documents with Outreach Tasks and prepare local messages."""
        imported = self.get_import(import_id)
        sender = self._db.execute(
            "SELECT address FROM mailboxes WHERE student_id = ?", (imported["student_id"],)).fetchone()["address"]
        tasks = list(self._db.execute(
            "SELECT t.id AS task_id, s.id AS supervisor_id, s.name AS supervisor_name, "
            "i.name AS institution_name "
            "FROM tasks t JOIN supervisors s ON s.id = t.supervisor_id JOIN institutions i ON i.id = s.institution_id "
            "WHERE t.campaign_id = ? AND t.student_id = ?",
            (imported["campaign_id"], imported["student_id"])))
        preparation_ids: list[str] = []
        unassociated_source_ids: list[str] = []
        with self._db:
            for source in self._db.execute(
                    "SELECT id, name FROM sources WHERE import_id = ? ORDER BY rowid", (import_id,)):
                if not source["name"].casefold().endswith(".docx"):
                    continue
                try:
                    parsed = parse_draft(read_paragraphs(self.read_source(source["id"])))
                except DocumentError as error:
                    self._record_document_finding(source["id"], "unsupported_document", str(error))
                    unassociated_source_ids.append(source["id"])
                    continue
                if parsed is None:
                    continue
                key = association_key(source["name"])
                matches = [task for task in tasks if key
                           and task["institution_name"].strip().casefold() == key[0].casefold()
                           and person_name(task["supervisor_name"]) == person_name(key[1])]
                if len(matches) != 1:
                    self._record_document_finding(
                        source["id"],
                        "unassociated_document" if not matches else "ambiguous_document",
                        f"{source['name']}: expected one Outreach Task, matched {len(matches)}")
                    unassociated_source_ids.append(source["id"])
                    continue
                task = matches[0]
                active = self._db.execute(
                    "SELECT id FROM preparations WHERE task_id = ? AND superseded_by IS NULL",
                    (task["task_id"],)).fetchone()
                already_active = self._db.execute(
                    "SELECT 1 FROM preparations WHERE task_id = ? AND source_id = ? AND superseded_by IS NULL",
                    (task["task_id"], source["id"])).fetchone()
                if active is not None and already_active is None:
                    self._record_document_finding(
                        source["id"], "replacement_requires_rewrite",
                        f"{source['name']}: Outreach Task already has active Preparation "
                        f"{active['id']}; replace it with an explicit Rewrite")
                    unassociated_source_ids.append(source["id"])
                    continue
                preparation_ids.append(self._store_preparation(task, source, parsed, sender, key))
        for preparation_id in preparation_ids:
            self.suggest_attachment_slots(preparation_id)
        return {"preparation_ids": preparation_ids, "unassociated_source_ids": unassociated_source_ids}

    def _record_document_finding(self, source_id: str, code: str, detail: str, blocking: bool = True) -> None:
        if self._db.execute("SELECT 1 FROM document_findings WHERE source_id = ? AND code = ?",
                            (source_id, code)).fetchone():
            return
        self._db.execute("INSERT INTO document_findings VALUES (?, ?, ?, ?, ?)",
                         (str(uuid4()), source_id, code, detail, 1 if blocking else 0))

    def list_unassociated_documents(self, import_id: str) -> list[dict]:
        self.get_import(import_id)
        return [
            {"id": row["id"], "source": {"id": row["source_id"], "name": row["source_name"]},
             "code": row["code"], "detail": row["detail"], "blocking": bool(row["blocking"])}
            for row in self._db.execute(
                "SELECT f.id, f.source_id, f.code, f.detail, f.blocking, s.name AS source_name "
                "FROM document_findings f JOIN sources s ON s.id = f.source_id "
                "WHERE s.import_id = ? ORDER BY s.rowid", (import_id,))]

    def _store_preparation(self, task: dict, source: dict, parsed: dict, sender: str, key: tuple) -> str:
        existing = self._db.execute(
            "SELECT id FROM preparations WHERE task_id = ? AND source_id = ? AND superseded_by IS NULL",
            (task["task_id"], source["id"])).fetchone()
        if existing:
            return existing["id"]
        return self._insert_preparation(task, source, parsed, sender, key)

    def _insert_preparation(self, task: dict, source: dict, parsed: dict, sender: str, key: tuple) -> str:
        preparation_id = str(uuid4())
        subject = ""
        recipient = email_address(parsed["recipient"])
        recorded = [row[0] for row in self._db.execute(
            "SELECT address FROM supervisor_addresses WHERE supervisor_id = ? ORDER BY address",
            (task["supervisor_id"],))]
        evidence = json.dumps(
            {"source": source["name"], "institution": key[0], "supervisor": key[1]}, ensure_ascii=False)
        self._db.execute(
            "INSERT INTO preparations (id, task_id, source_id, sender, recipient, subject, body, "
            "internal_note, association_evidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (preparation_id, task["task_id"], source["id"], sender,
             recipient or parsed["recipient"], subject, parsed["body"], parsed["internal_note"], evidence))
        self._record_transformation(
            preparation_id, "recipient_extracted",
            f"Recipient declared in {source['name']}: {parsed['recipient']}")
        self._record_transformation(
            preparation_id, "body_restructured",
            "Message body retained from the greeting through the sign-off; spacing normalized")
        if parsed["note_separated"]:
            self._record_transformation(
                preparation_id, "internal_note_separated",
                f"Internal note removed from the message body: {parsed['internal_note']}")
        if recipient and not recorded:
            self._record_transformation(
                preparation_id, "recipient_filled_missing_address",
                f"Recipient {recipient} taken from {source['name']}; no usable address was recorded")
        self._revalidate(preparation_id)
        return preparation_id

    def rewrite(self, preparation_id: str, source_id: str) -> dict:
        """Replace an active Preparation with a fresh one, keeping the prior version inspectable."""
        prior = self._db.execute(
            "SELECT id, task_id, superseded_by, action_kind, linked_sent_record_id "
            "FROM preparations WHERE id = ?",
            (preparation_id,)).fetchone()
        if prior is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        if prior["superseded_by"] is not None:
            raise SmartMailError(f"Preparation is already superseded: {preparation_id}")
        if self._db.execute(
                "SELECT 1 FROM execution_attempts WHERE preparation_id = ? "
                "AND state IN ('in_progress', 'unknown')", (preparation_id,)).fetchone():
            raise SmartMailError(
                "An Execution Attempt for this Preparation is unresolved; stop or resolve it "
                "before rewriting")
        if self._db.execute(
                "SELECT 1 FROM sent_records WHERE preparation_id = ?",
                (preparation_id,)).fetchone():
            raise SmartMailError(
                "Sent content is frozen; prepare a new linked Communication Action instead "
                "of rewriting")
        task = self._db.execute(
            "SELECT t.id AS task_id, t.supervisor_id, s.name AS supervisor_name, i.name AS institution_name, "
            "(SELECT address FROM mailboxes WHERE student_id = t.student_id) AS sender "
            "FROM tasks t JOIN supervisors s ON s.id = t.supervisor_id "
            "JOIN institutions i ON i.id = s.institution_id WHERE t.id = ?", (prior["task_id"],)).fetchone()
        source = self._db.execute("SELECT id, name FROM sources WHERE id = ?", (source_id,)).fetchone()
        if source is None:
            raise SmartMailError(f"Source Material not found: {source_id}")
        try:
            parsed = parse_draft(read_paragraphs(self.read_source(source_id)))
        except DocumentError as error:
            raise SmartMailError(f"Cannot rewrite from Source Material: {error}") from error
        key = association_key(source["name"])
        if parsed is None or key is None or key[0].strip().casefold() != task["institution_name"].strip().casefold() \
                or person_name(key[1]) != person_name(task["supervisor_name"]):
            raise SmartMailError(
                f"Source Material does not describe this Outreach Task: {source['name']}")
        with self._db:
            fresh_id = self._insert_preparation(task, source, parsed, task["sender"], key)
            self._db.execute(
                "UPDATE preparations SET superseded_by = ? WHERE id = ?", (fresh_id, preparation_id))
            if prior["action_kind"] != "initial":
                # A rewritten Follow-up stays the same separate linked Communication
                # Action; it must never become duplicate-checkable initial outreach.
                self._db.execute(
                    "UPDATE preparations SET action_kind = 'follow_up', "
                    "linked_sent_record_id = ? WHERE id = ?",
                    (prior["linked_sent_record_id"], fresh_id))
                self._db.execute(
                    "UPDATE follow_up_actions SET preparation_id = ? WHERE preparation_id = ?",
                    (fresh_id, preparation_id))
                self._record_transformation(
                    fresh_id, "follow_up_linked",
                    "Rewritten Preparation keeps the separate linked Follow-up Action for "
                    f"Sent Record {prior['linked_sent_record_id']}")
            self._db.execute(
                "UPDATE confirmations SET status = 'invalidated', invalidated_reason = 'rewrite' "
                "WHERE preparation_id = ? AND status = 'active'", (preparation_id,))
            self._db.execute(
                "DELETE FROM document_findings WHERE source_id = ? AND code = 'replacement_requires_rewrite'",
                (source_id,))
            self._clear_follow_up_reply_pause_if_resolved(prior["task_id"])
        self.suggest_attachment_slots(fresh_id)
        return self.get_preparation(fresh_id)

    def _revalidate(self, preparation_id: str) -> None:
        """Recompute the complete Preparation's readiness findings from its current local state."""
        preparation = self._db.execute(
            "SELECT * FROM preparations WHERE id = ?", (preparation_id,)).fetchone()
        if preparation is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        self._db.execute("DELETE FROM readiness_findings WHERE preparation_id = ?", (preparation_id,))
        recorded = [row[0] for row in self._db.execute(
            "SELECT a.address FROM supervisor_addresses a JOIN tasks t ON t.supervisor_id = a.supervisor_id "
            "WHERE t.id = ? ORDER BY a.address", (preparation["task_id"],))]
        recipient = email_address(preparation["recipient"])
        if not preparation["subject"].strip():
            self._record_finding(
                preparation_id, "missing_subject",
                "No authoritative subject is available for this Preparation")
        if recipient is None:
            self._record_finding(
                preparation_id, "invalid_recipient",
                f"Draft recipient is not a usable address: {preparation['recipient']}")
        elif recorded and recipient.casefold() not in {address.casefold() for address in recorded}:
            self._record_finding(
                preparation_id, "recipient_conflict",
                f"Draft recipient {recipient} differs from recorded Supervisor address(es): "
                f"{', '.join(recorded)}")
        if self._db.execute(
                "SELECT 1 FROM exceptions WHERE task_id = ? AND code = 'identity_ambiguity' AND blocking = 1",
                (preparation["task_id"],)).fetchone():
            self._record_finding(
                preparation_id, "identity_conflict",
                "The associated Outreach Task has an unresolved Supervisor identity conflict")

    def set_subject(self, preparation_id: str, subject: str) -> dict:
        """Record an explicit operator subject as the field's Authoritative Source."""
        subject = subject.strip()
        if not subject:
            raise SmartMailError("A non-blank subject is required; SmartMail never invents one")
        with self._db:
            self._correct_field(preparation_id, "subject", subject)
        return self.get_preparation(preparation_id)

    def set_recipient(self, preparation_id: str, address: str) -> dict:
        """Record an explicit operator recipient; the value is normalized, never guessed."""
        normalized = email_address(address)
        if normalized is None:
            raise SmartMailError("A usable email address is required; SmartMail never guesses a recipient")
        with self._db:
            self._correct_field(preparation_id, "recipient", normalized)
        return self.get_preparation(preparation_id)

    def _correct_field(self, preparation_id: str, field: str, value: str) -> None:
        row = self._db.execute(
            f"SELECT {field} FROM preparations WHERE id = ?", (preparation_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        prior = row[field]
        if prior == value:
            return
        self._db.execute(f"UPDATE preparations SET {field} = ? WHERE id = ?", (value, preparation_id))
        self._record_correction(preparation_id, field, value, prior)
        self._revalidate(preparation_id)

    def _record_correction(self, preparation_id: str, field: str, value: str, prior: str) -> None:
        self._db.execute("INSERT INTO corrections VALUES (?, ?, ?, ?, ?)",
                         (str(uuid4()), preparation_id, field, value, prior))

    def _record_transformation(self, preparation_id: str, code: str, detail: str) -> None:
        self._db.execute("INSERT INTO transformations VALUES (?, ?, ?, ?)",
                         (str(uuid4()), preparation_id, code, detail))

    def _record_finding(self, preparation_id: str, code: str, detail: str, blocking: bool = True) -> None:
        self._db.execute("INSERT INTO readiness_findings VALUES (?, ?, ?, ?, ?)",
                         (str(uuid4()), preparation_id, code, detail, 1 if blocking else 0))

    def list_preparations(self, campaign_id: str) -> list[dict]:
        self.get_campaign(campaign_id)
        return [dict(row) for row in self._db.execute(
            "SELECT p.id, p.task_id, p.sender, p.recipient, p.subject, p.source_id, t.student_id, "
            "s.name AS supervisor_name, st.name AS student_name, src.name AS source_name, "
            "(SELECT count(*) FROM readiness_findings f WHERE f.preparation_id = p.id AND f.blocking = 1) "
            "AS blocking_count "
            "FROM preparations p JOIN tasks t ON t.id = p.task_id "
            "JOIN supervisors s ON s.id = t.supervisor_id JOIN students st ON st.id = t.student_id "
            "JOIN sources src ON src.id = p.source_id "
            "WHERE t.campaign_id = ? AND p.superseded_by IS NULL ORDER BY t.rowid",
            (campaign_id,))]

    def preview_preparation(self, preparation_id: str) -> dict:
        """The full local message, with readiness and the separated internal note kept apart."""
        preparation = self.get_preparation(preparation_id)
        blocking = [finding["code"] for finding in preparation["readiness_findings"] if finding["blocking"]]
        readiness = "Blocked: " + ", ".join(blocking) if blocking else "Ready"
        subject = preparation["subject"] or "(no authoritative subject)"
        confirmed = [slot["attachment"]["name"] for slot in preparation["attachment_slots"]
                     if slot["attachment"]]
        suggested = [
            f"{slot['label']} \u2192 " + (slot["candidates"][0]["name"] if slot["suggested_source_id"]
                                          else "no single candidate")
            for slot in preparation["attachment_slots"] if not slot["attachment"]]
        lines = [
            f"From: {preparation['sender']}",
            f"To: {preparation['recipient']}",
            f"Subject: {subject}",
            f"Readiness: {readiness}",
            f"Source: {preparation['source']['name']}",
            f"Attachments: {', '.join(confirmed) if confirmed else '(none)'}",
        ]
        if suggested:
            lines.append(f"Suggested attachments: {'; '.join(suggested)}")
        text = "\n".join([*lines, "", preparation["body"]])
        return {"sender": preparation["sender"], "recipient": preparation["recipient"],
                "subject": preparation["subject"], "body": preparation["body"],
                "internal_note": preparation["internal_note"], "readiness": readiness,
                "attachments": confirmed, "suggested_attachments": suggested, "text": text}

    def get_preparation(self, preparation_id: str) -> dict:
        row = self._db.execute("SELECT * FROM preparations WHERE id = ?", (preparation_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        preparation = dict(row)
        preparation["source"] = dict(self._db.execute(
            "SELECT id, name, sha256 FROM sources WHERE id = ?", (row["source_id"],)).fetchone())
        preparation["association"] = json.loads(preparation.pop("association_evidence"))
        preparation["transformations"] = [dict(r) for r in self._db.execute(
            "SELECT code, detail FROM transformations WHERE preparation_id = ? ORDER BY rowid", (preparation_id,))]
        preparation["readiness_findings"] = [dict(r) for r in self._db.execute(
            "SELECT code, detail, blocking FROM readiness_findings WHERE preparation_id = ? ORDER BY rowid",
            (preparation_id,))]
        preparation["corrections"] = [dict(r) for r in self._db.execute(
            "SELECT field, value, prior FROM corrections WHERE preparation_id = ? ORDER BY rowid",
            (preparation_id,))]
        preparation["attachment_slots"] = self.list_attachment_slots(preparation_id)
        preparation["status"] = "superseded" if preparation["superseded_by"] else "active"
        preparation["ready"] = not any(finding["blocking"] for finding in preparation["readiness_findings"])
        return preparation

    def get_preparation_history(self, preparation_id: str) -> dict:
        """Every version of an Outreach Task's Preparation, newest first, with its evidence."""
        row = self._db.execute(
            "SELECT task_id FROM preparations WHERE id = ?", (preparation_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Preparation not found: {preparation_id}")
        versions = [self.get_preparation(r["id"]) for r in self._db.execute(
            "SELECT id FROM preparations WHERE task_id = ? ORDER BY rowid DESC", (row["task_id"],))]
        active_id = next((version["id"] for version in versions if version["status"] == "active"), None)
        return {"task_id": row["task_id"], "active_id": active_id, "versions": versions}
