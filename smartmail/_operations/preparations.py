"""Document association, Preparation, readiness corrections and Rewrite history."""

import hashlib
import json
import re
from uuid import uuid4

from ..documents import DocumentError, association_key, parse_draft, read_paragraphs
from ..identity import email_address, person_name
from ..recognition import extract_letters
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
        # A master-based import makes the workbook authoritative for task
        # identity; unmatched drafts stay findings.  A master-less import has
        # no workbook associations, so the addressed letters establish Tasks.
        has_master = self._db.execute(
            "SELECT 1 FROM source_associations a JOIN sources s ON s.id = a.source_id "
            "WHERE s.import_id = ? AND a.sheet != 'document' LIMIT 1", (imported["id"],)).fetchone()
        preparation_ids: list[str] = []
        unassociated_source_ids: list[str] = []
        with self._db:
            for source in self._db.execute(
                    "SELECT id, name FROM sources WHERE import_id = ? ORDER BY rowid", (imported["id"],)):
                if not source["name"].casefold().endswith(".docx"):
                    continue
                try:
                    data = self.read_source(source["id"])
                    parsed = parse_draft(read_paragraphs(data))
                except DocumentError as error:
                    self._record_document_finding(source["id"], "unsupported_document", str(error))
                    unassociated_source_ids.append(source["id"])
                    continue
                key = association_key(source["name"])
                matches = [task for task in tasks if parsed and key
                           and task["institution_name"].strip().casefold() == key[0].casefold()
                           and person_name(task["supervisor_name"]) == person_name(key[1])]
                if parsed is not None and len(matches) == 1:
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
                    continue
                if parsed is not None and has_master:
                    self._record_document_finding(
                        source["id"],
                        "unassociated_document" if not matches else "ambiguous_document",
                        f"{source['name']}: expected one Outreach Task, matched {len(matches)}")
                    unassociated_source_ids.append(source["id"])
                    continue
                if not has_master:
                    if parsed is not None:
                        letters = [{
                            "supervisor": key[1] if key else "",
                            "institution": key[0] if key else "",
                            "recipient": parsed["recipient"],
                            "subject": "",
                            "body": parsed["body"],
                            "internal_note": parsed["internal_note"],
                        }]
                    else:
                        letters = extract_letters(data)
                    for letter_index, letter in enumerate(letters, start=1):
                        outcome = self._prepare_letter(
                            letter, letter_index, source, sender, imported, tasks)
                        if outcome["prepared"]:
                            preparation_ids.append(outcome["prepared"])
                            tasks.append(outcome["task_row"])
                        elif outcome["code"]:
                            self._record_document_finding(source["id"], outcome["code"], outcome["detail"])
                            if source["id"] not in unassociated_source_ids:
                                unassociated_source_ids.append(source["id"])
        for preparation_id in preparation_ids:
            self.suggest_attachment_slots(preparation_id)
        return {"preparation_ids": preparation_ids, "unassociated_source_ids": unassociated_source_ids}

    def _prepare_letter(self, letter, letter_index, source, sender, imported, tasks) -> dict:
        """Store one addressed letter as a Preparation, creating its Task if needed."""
        institution = (letter.get("institution") or "").strip()
        supervisor = (letter.get("supervisor") or letter.get("salutation_name") or "").strip()
        recipient = email_address(letter.get("recipient") or "") or ""
        if not supervisor:
            return {"prepared": "", "task_row": None, "code": "unassociated_document",
                    "detail": f"{source['name']}: letter {letter_index} has no supervisor identity"}
        matches = [task for task in tasks
                   if task["institution_name"].strip().casefold() == institution.casefold()
                   and person_name(task["supervisor_name"]) == person_name(supervisor)]
        if len(matches) > 1:
            return {"prepared": "", "task_row": None, "code": "ambiguous_document",
                    "detail": f"{source['name']}: letter {letter_index} matched {len(matches)} Outreach Tasks"}
        if not matches:
            ensured = self.ensure_task_from_correspondent(
                imported["campaign_id"], imported["student_id"], source["id"],
                institution, supervisor, recipient, letter_index)
            if ensured is None:
                return {"prepared": "", "task_row": None, "code": "unassociated_document",
                        "detail": f"{source['name']}: letter {letter_index} has no supervisor identity"}
            task_row = {"task_id": ensured["task_id"], "supervisor_id": ensured["supervisor_id"],
                        "supervisor_name": ensured["supervisor_name"],
                        "institution_name": ensured["institution_name"]}
        else:
            task_row = matches[0]
        active = self._db.execute(
            "SELECT id FROM preparations WHERE task_id = ? AND superseded_by IS NULL",
            (task_row["task_id"],)).fetchone()
        already_active = self._db.execute(
            "SELECT 1 FROM preparations WHERE task_id = ? AND source_id = ? AND superseded_by IS NULL",
            (task_row["task_id"], source["id"])).fetchone()
        if active is not None and already_active is None:
            return {"prepared": "", "task_row": None, "code": "replacement_requires_rewrite",
                    "detail": f"{source['name']}: Outreach Task already has active Preparation "
                              f"{active['id']}; replace it with an explicit Rewrite"}
        parsed = {"recipient": recipient, "body": letter["body"],
                  "internal_note": letter.get("internal_note", ""),
                  "note_separated": bool(letter.get("internal_note"))}
        prepared = self._insert_preparation(
            task_row, source, parsed, sender, (institution, supervisor),
            subject=letter.get("subject", ""))
        return {"prepared": prepared, "task_row": task_row, "code": "", "detail": ""}

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

    def _insert_preparation(self, task: dict, source: dict, parsed: dict, sender: str,
                            key: tuple, subject: str = "") -> str:
        preparation_id = str(uuid4())
        subject = (subject or "").strip()
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
        if preparation["action_kind"] == "initial" and self._db.execute(
                "SELECT 1 FROM exceptions WHERE task_id = ? "
                "AND code = 'prior_outreach_conflict' AND blocking = 1",
                (preparation["task_id"],)).fetchone():
            self._record_finding(
                preparation_id, "prior_outreach_conflict",
                "The Outreach Task has unresolved evidence that initial outreach was already "
                "sent; resolve the import conflict before new initial outreach")

    def set_subject(self, preparation_id: str, subject: str) -> dict:
        """Record an explicit operator subject as the field's Authoritative Source."""
        subject = subject.strip()
        if not subject:
            raise SmartMailError("A non-blank subject is required; SmartMail never invents one")
        with self._db:
            self._correct_field(preparation_id, "subject", subject)
        return self.get_preparation(preparation_id)

    def update_preparation_subjects(self, updates: list[dict]) -> dict:
        """Record operator subjects for several Preparations as one reviewed batch.

        The batch is only a convenience around the same per-Preparation correction
        rules: subjects stay operator-supplied, readiness is recomputed per
        Preparation, and a changed subject invalidates that Preparation's active
        Confirmation. The whole batch is validated before any write and shares one
        transaction, so a rejected entry leaves every Preparation untouched.
        """
        if not isinstance(updates, list) or not updates:
            raise SmartMailError("Select at least one Preparation to correct")
        entries: list[tuple[str, str]] = []
        for entry in updates:
            if not isinstance(entry, dict):
                raise SmartMailError("Each batch entry must name a Preparation and a subject")
            preparation_id = entry.get("preparation_id")
            subject = entry.get("subject")
            if not isinstance(preparation_id, str) or not isinstance(subject, str) \
                    or not subject.strip():
                raise SmartMailError(
                    "A non-blank subject is required; SmartMail never invents one")
            entries.append((preparation_id, subject.strip()))
        if len({preparation_id for preparation_id, _ in entries}) != len(entries):
            raise SmartMailError("A Preparation may appear only once in a subject batch")
        # Validate the whole batch first: an unusable entry must not leave an
        # earlier Preparation corrected.
        for preparation_id, _ in entries:
            self._require_local_preparation(preparation_id)
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            for preparation_id, subject in entries:
                if self._db.execute("SELECT subject FROM preparations WHERE id = ?",
                                    (preparation_id,)).fetchone()["subject"] == subject:
                    continue
                self._correct_field(preparation_id, "subject", subject)
                self._db.execute(
                    "UPDATE confirmations SET status = 'invalidated', invalidated_reason = 'content_changed' "
                    "WHERE preparation_id = ? AND status = 'active'", (preparation_id,))
        return {"count": len(entries), "preparations": [
            self.get_preparation(preparation_id) for preparation_id, _ in entries]}

    def update_preparation_fields(self, preparation_id: str, subject: str, recipient: str) -> dict:
        """Atomically correct a local draft using existing correction/readiness rules.

        Sent, superseded and externally committed content must follow the existing
        linked-action, Rewrite or scheduled replacement flows instead.
        """
        if not isinstance(subject, str) or not subject.strip():
            raise SmartMailError("A non-blank subject is required")
        normalized = email_address(recipient) if isinstance(recipient, str) else None
        if not normalized:
            raise SmartMailError("A usable email address is required")
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            preparation = self._require_local_preparation(preparation_id)
            changed = preparation["subject"] != subject.strip() or preparation["recipient"] != normalized
            self._correct_field(preparation_id, "subject", subject.strip())
            self._correct_field(preparation_id, "recipient", normalized)
            if changed:
                self._db.execute(
                    "UPDATE confirmations SET status = 'invalidated', invalidated_reason = 'content_changed' "
                    "WHERE preparation_id = ? AND status = 'active'", (preparation_id,))
        return self.get_preparation(preparation_id)

    def _require_local_preparation(self, preparation_id: str) -> dict:
        """Keep ordinary local editing separate from external commitment replacement."""
        preparation = self.get_preparation(preparation_id)
        if preparation["status"] != "active":
            raise SmartMailError("Superseded Preparation is retained as history")
        if self._db.execute(
                "SELECT 1 FROM sent_records WHERE preparation_id = ?", (preparation_id,)).fetchone():
            raise SmartMailError("Sent content is frozen; create a linked Communication Action")
        if self._db.execute(
                "SELECT 1 FROM execution_attempts WHERE preparation_id = ? "
                "AND state IN ('in_progress', 'unknown', 'externally_scheduled', 'sent', 'cancel_unknown')",
                (preparation_id,)).fetchone() or self._db.execute(
                "SELECT 1 FROM external_schedules WHERE preparation_id = ? "
                "AND state != 'cancelled'", (preparation_id,)).fetchone():
            raise SmartMailError("Resolve the external commitment before adjusting this Preparation")
        return preparation

    def rewrite_local_preparation(self, preparation_id: str, source_id: str) -> dict:
        """Reuse Rewrite after enforcing the ordinary local-draft editing boundary."""
        with self._db:
            self._db.execute("BEGIN IMMEDIATE")
            self._require_local_preparation(preparation_id)
            return self.rewrite(preparation_id, source_id)

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

    # ------------------------------------------------------------------
    # Observed mailbox drafts as Source Material
    # ------------------------------------------------------------------

    def draft_material_candidates(self, campaign_id: str, student_id: str) -> list[dict]:
        """Observed drafts this Student can promote, with what Core actually holds.

        A draft observed in the Student's own drafts folder is Source Material:
        Core captured its body during the observation, so it can be imported the
        same way an upload is. Attachment *bytes* are never assumed — only a
        descriptor the reader produced is reported, and its availability is stated.
        """
        campaign = self.get_campaign(campaign_id)
        self.get_student(student_id)
        rows = self._latest_draft_observations(student_id)
        candidates = []
        for row in rows:
            material = self._observation_material(row)
            body = self._draft_body(material)
            recipients = self._draft_recipients(material, row)
            recipient = recipients[0] if recipients else ""
            task = self._task_for_address(campaign_id, student_id, recipient) if recipient else None
            attachments = material.get("attachments") or []
            candidates.append({
                "observation_id": row["id"],
                "subject": row["subject"],
                "recipient": recipient,
                "recipients": recipients,
                "observed_time": row["observed_time"],
                "status": row["status"],
                "scheduled": bool((material.get("compose") or {}).get("scheduled_draft")),
                "body_chars": len(body),
                "body_available": bool(body.strip()),
                "attachment_count": len(attachments),
                "attachments_available": sum(1 for entry in attachments if entry.get("available")),
                "task_id": task["task_id"] if task else "",
                "supervisor": task["supervisor_name"] if task else "",
                "campaign_id": campaign["id"],
            })
        return candidates

    def import_mailbox_drafts(self, campaign_id: str, student_id: str,
                              observation_ids: list[str]) -> dict:
        """Promote observed drafts into Source Material and their Preparations.

        The draft's own mailbox is the evidence of its type: a message the
        Student composed, addressed to a Supervisor, is an outreach draft. No
        structural recognition is needed and none is invented. Imports are
        idempotent by content hash, so re-importing an unchanged draft reuses
        the Source Material instead of duplicating it.
        """
        self.get_campaign(campaign_id)
        self.get_student(student_id)
        wanted = [str(entry) for entry in (observation_ids or [])]
        if not wanted:
            raise SmartMailError("Select at least one observed draft to import")
        rows = {row["id"]: row for row in self._latest_draft_observations(student_id)}
        sender = self._db.execute(
            "SELECT address FROM mailboxes WHERE student_id = ?", (student_id,)).fetchone()
        if sender is None:
            raise SmartMailError("No Mailbox is recorded for this Student")
        sender = sender["address"]
        import_id = str(uuid4())
        imported = []
        skipped = []
        with self._db:
            self._db.execute("INSERT INTO imports VALUES (?, ?, ?)", (import_id, campaign_id, student_id))
            for observation_id in wanted:
                row = rows.get(observation_id)
                if row is None:
                    skipped.append({"observation_id": observation_id, "subject": "",
                                    "reason": "No observed draft in the latest observation"})
                    continue
                material = self._observation_material(row)
                body = self._draft_body(material)
                recipients = self._draft_recipients(material, row)
                recipient = recipients[0] if recipients else ""
                if not recipient:
                    skipped.append({"observation_id": observation_id, "subject": row["subject"],
                                    "reason": "The draft has no usable recipient address"})
                    continue
                task = self._task_for_address(campaign_id, student_id, recipient)
                if task is None:
                    skipped.append({"observation_id": observation_id, "subject": row["subject"],
                                    "reason": f"No Outreach Task recorded for {recipient}"})
                    continue
                if not body.strip():
                    skipped.append({"observation_id": observation_id, "subject": row["subject"],
                                    "reason": "The draft body was not captured in the observation"})
                    continue
                payload = _draft_source_bytes(row, recipients, body)
                sha = hashlib.sha256(payload).hexdigest()
                existing = self._db.execute(
                    "SELECT id FROM sources WHERE sha256 = ?", (sha,)).fetchone()
                if existing is not None:
                    skipped.append({"observation_id": observation_id, "subject": row["subject"],
                                    "reason": "This draft is already imported as Source Material"})
                    continue
                source_id = str(uuid4())
                self._db.execute(
                    "INSERT INTO sources VALUES (?, ?, ?, ?, ?)",
                    (source_id, import_id, _draft_source_name(row), payload, sha))
                self._persist_draft_recognition(source_id, row)
                self._db.execute(
                    "INSERT INTO source_associations (task_id, source_id, sheet, row, evidence) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (task["task_id"], source_id, "drafts", 0, json.dumps(
                        {"observation_id": row["id"], "observed_time": row["observed_time"]},
                        ensure_ascii=False)))
                preparation_id = self._insert_preparation(
                    task, {"id": source_id, "name": _draft_source_name(row)},
                    {"recipient": recipient, "body": body, "internal_note": "",
                     "note_separated": False}, sender,
                    (task["institution_name"], task["supervisor_name"]),
                    subject=row["subject"])
                self._record_transformation(
                    preparation_id, "draft_imported",
                    f"Body and recipients taken from the observed draft in {row['folder']}; "
                    "the Student's own mailbox is the authoritative source")
                attachments = material.get("attachments") or []
                if attachments:
                    missing = [entry["name"] for entry in attachments if not entry.get("available")]
                    detail = f"{len(attachments)} attachment(s) observed in the draft"
                    if missing:
                        detail += "; bytes not captured, so they are not imported: " + ", ".join(missing)
                    self._record_transformation(preparation_id, "draft_attachments_observed", detail)
                imported.append({"observation_id": observation_id, "subject": row["subject"],
                                 "recipient": recipient, "task_id": task["task_id"],
                                 "source_id": source_id, "preparation_id": preparation_id})
        return {"import": {"id": import_id, "campaign_id": campaign_id, "student_id": student_id},
                "imported": imported, "skipped": skipped}

    def _latest_draft_observations(self, student_id: str) -> list[dict]:
        mailbox = self._db.execute(
            "SELECT id FROM mailboxes WHERE student_id = ?", (student_id,)).fetchone()
        if mailbox is None:
            return []
        run = self._db.execute(
            "SELECT id FROM mailbox_observation_runs WHERE mailbox_id = ? "
            "ORDER BY observed_at DESC, rowid DESC LIMIT 1", (mailbox["id"],)).fetchone()
        if run is None:
            return []
        return [dict(row) for row in self._db.execute(
            "SELECT * FROM mailbox_message_observations WHERE run_id = ? AND folder = 'drafts' "
            "ORDER BY rowid", (run["id"],))]

    @staticmethod
    def _observation_material(row: dict) -> dict:
        try:
            evidence = json.loads(row["evidence"] or "{}")
        except (ValueError, TypeError):
            return {}
        material = evidence.get("material") if isinstance(evidence, dict) else None
        return material if isinstance(material, dict) else {}

    @staticmethod
    def _draft_body(material: dict) -> str:
        compose = material.get("compose") or {}
        body = str(compose.get("body_text") or "").strip()
        if body:
            return body
        return str((material.get("content") or {}).get("text") or "").strip()

    @staticmethod
    def _draft_recipients(material: dict, row: dict) -> list[str]:
        compose = material.get("compose") or {}
        addresses = [entry for entry in (compose.get("to") or []) if entry]
        if not addresses:
            counterpart = email_address(str(row["counterpart"] or ""))
            addresses = [counterpart] if counterpart else []
        return addresses

    def _task_for_address(self, campaign_id: str, student_id: str, address: str):
        return self._db.execute(
            "SELECT t.id AS task_id, t.supervisor_id, s.name AS supervisor_name, "
            "i.name AS institution_name "
            "FROM tasks t JOIN supervisors s ON s.id = t.supervisor_id "
            "JOIN institutions i ON i.id = s.institution_id "
            "JOIN supervisor_addresses a ON a.supervisor_id = t.supervisor_id "
            "WHERE t.campaign_id = ? AND t.student_id = ? AND a.address = ?",
            (campaign_id, student_id, address)).fetchone()

    def _persist_draft_recognition(self, source_id: str, row: dict) -> None:
        """The mailbox is the evidence of type: no structural recognition is invented."""
        self._db.execute(
            "INSERT INTO source_recognition "
            "(source_id, recognized_type, effective_type, confidence, revised, reasons, cautions, detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(source_id) DO UPDATE SET "
            "recognized_type = excluded.recognized_type, effective_type = excluded.effective_type, "
            "confidence = excluded.confidence, revised = excluded.revised, "
            "reasons = excluded.reasons, cautions = excluded.cautions, detail = excluded.detail",
            (source_id, "outreach_draft", "outreach_draft", "high", 0,
             json.dumps([f"Observed as a draft in the Student's own {row['folder']} folder",
                         f"Addressed to {row['counterpart'] or 'a recorded recipient'}"],
                        ensure_ascii=False),
             json.dumps([] if (row["status"] == "draft") else
                        [f"Observed status is {row['status']}, not a plain draft"], ensure_ascii=False),
             json.dumps({"label": "Outreach draft", "actionable": True, "identities": {
                 "subject": row["subject"], "addressee": {"email": row["counterpart"]}}},
                        ensure_ascii=False)))


def _draft_source_name(row: dict) -> str:
    """A stable Source Material name for an observed draft."""
    subject = re.sub(r"[^A-Za-z0-9一-鿿._-]+", "_", str(row["subject"] or "").strip()).strip("._")
    return f"{subject or 'draft'}-{row['id'][:8]}.eml"


def _draft_source_bytes(row: dict, recipients: list[str], body: str) -> bytes:
    headers = [f"Subject: {row['subject']}", f"To: {', '.join(recipients)}",
               f"Date: {row['observed_time']}", f"X-SmartMail-Observation: {row['id']}",
               f"X-SmartMail-Folder: {row['folder']}", ""]
    return ("\n".join(headers) + "\n" + body).encode("utf-8")
