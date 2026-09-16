"""Native schedules, Cancellation, Scheduled Replacement and Recall.

The extension carries out one confirmed operation and returns evidence;
local plans, Externally Scheduled, Unknown Outcome and Sent stay distinct.
"""

import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from ..errors import SmartMailError
from ..mailbox import MailboxCapabilityError

#: External schedule lifecycle, persisted in external_schedules.state.
SCHEDULE_STATES = {
    "placement_unknown", "externally_scheduled", "sent",
    "cancelled", "cancel_unknown", "replaced",
}
#: Outcomes that prove the mailbox owns the scheduled commitment.
ACTIVE_SCHEDULE_STATES = {"placement_unknown", "externally_scheduled"}
CANCELLABLE_STATES = {"externally_scheduled"}


class SchedulesOperations:
    """Place and track native schedules, and control their external commitment."""

    # --------------------------------------------------------------- placement
    def place_schedule(self, confirmation_id: str) -> dict:
        """Place a confirmed native schedule through the connected extension."""
        return self._place_schedule_attempt(self.get_confirmation(confirmation_id))

    def _schedule_instant(self, execution: dict) -> datetime:
        text = execution.get("scheduled_utc") or execution.get("scheduled_at") \
            or execution.get("scheduled_time")
        if not text:
            raise SmartMailError("Confirmation is not bound to an exact schedule time")
        parsed = self._parse_timestamp(text)
        if parsed is None:
            raise SmartMailError(f"Unsupported schedule time in Confirmation: {text}")
        if execution.get("timezone") and not execution.get("scheduled_utc"):
            zone = ZoneInfo(execution["timezone"])
            naive = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
            parsed = naive.replace(tzinfo=zone)
        return parsed.astimezone(timezone.utc)

    def _schedule_request(self, preparation: dict, execution: dict) -> dict:
        instant = self._schedule_instant(execution)
        attachments = [
            {"label": slot["label"], "name": slot["attachment"]["name"],
             "sha256": slot["attachment"]["sha256"], "size": slot["attachment"]["size"]}
            for slot in preparation["attachment_slots"] if slot["attachment"]]
        return {"sender": preparation["sender"], "recipient": preparation["recipient"],
                "subject": preparation["subject"], "body": preparation["body"],
                "attachments": attachments, "kind": "scheduled",
                "scheduled_utc": instant.isoformat(),
                "scheduled_epoch_ms": int(instant.timestamp() * 1000)}

    def _start_attempt(self, confirmation: dict, request: dict) -> str:
        """Persist the intent row, then the independently committed start marker."""
        now = self._now()
        existing = self._db.execute(
            "SELECT * FROM execution_attempts WHERE confirmation_id = ? ORDER BY rowid DESC LIMIT 1",
            (confirmation["id"],)).fetchone()
        if existing and existing["state"] in ("in_progress", "unknown", "externally_scheduled",
                                             "cancel_unknown"):
            raise SmartMailError(
                "An unresolved external operation exists; reconcile it before another attempt")
        attempt_id = str(uuid4())
        evidence = {"outcome": "not_attempted", "phase": "intent_recorded",
                    "intent_persisted_at": now}
        self._db.execute(
            "INSERT INTO execution_attempts "
            "(id, confirmation_id, preparation_id, task_id, sequence, state, request, "
            "evidence, phase, intent_at, submission_started_at, outcome_observed_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, 'not_attempted', ?, ?, 'intent_recorded', ?, '', '', ?)",
            (attempt_id, confirmation["id"], confirmation["preparation_id"],
             confirmation["task_id"], self._next_sequence(confirmation["preparation_id"]),
             json.dumps(request, ensure_ascii=False),
             json.dumps(evidence, ensure_ascii=False), now, now))
        self._db.commit()
        evidence.update({"phase": "submission_started", "submission_started_at": now})
        self._db.execute(
            "UPDATE execution_attempts SET state = 'in_progress', evidence = ?, "
            "phase = 'submission_started', updated_at = ? WHERE id = ?",
            (json.dumps(evidence, ensure_ascii=False), now, attempt_id))
        self._db.commit()
        return attempt_id

    def _place_schedule_attempt(self, confirmation: dict, *, replaces: dict | None = None) -> dict:
        campaign_id = self._campaign_of_task(confirmation["task_id"])
        flow = self._flow_state(campaign_id)
        if flow["state"] == "paused":
            raise SmartMailError(
                f"Execution Flow is paused ({flow['reason']}); resolve it before executing")
        if confirmation["status"] != "active":
            raise SmartMailError("Confirmation is not active; renew it before placing the schedule")
        execution = confirmation["execution"]
        if execution.get("kind") != "scheduled":
            raise SmartMailError("Only a scheduled Confirmation can place a native schedule")
        preparation = self.get_preparation(confirmation["preparation_id"])
        if preparation["status"] != "active":
            raise SmartMailError("Preparation has been superseded; the prior Confirmation does not transfer")
        if self._content_digest(preparation) != confirmation["content_digest"] \
                or self._attachments_digest(preparation) != confirmation["attachments_digest"]:
            raise SmartMailError("Preparation content changed after Confirmation")
        blocking = [f["code"] for f in preparation["readiness_findings"] if f["blocking"]]
        if blocking:
            raise SmartMailError(f"Preparation is not Ready; resolve: {', '.join(blocking)}")
        if self._db.execute("SELECT 1 FROM sent_records WHERE preparation_id = ?",
                            (preparation["id"],)).fetchone():
            raise SmartMailError("Preparation has already been Sent")
        duplicate = self.check_duplicate(preparation["id"])
        if duplicate["review_required"]:
            self._pause_flow(campaign_id, duplicate["finding"], {"detail": duplicate["detail"]})
            self._db.commit()
            raise SmartMailError(f"Duplicate Suspicion requires resolution: {duplicate['finding']}")
        if not replaces and self._db.execute(
                "SELECT 1 FROM external_schedules WHERE preparation_id = ? "
                "AND state IN ('externally_scheduled', 'sent', 'placement_unknown')",
                (preparation["id"],)).fetchone():
            raise SmartMailError("An external schedule for this Preparation is already tracked")
        instant = self._schedule_instant(execution)
        if instant <= self._instant():
            raise SmartMailError(
                "The confirmed schedule time has elapsed; confirm an explicit replacement time")
        if not getattr(self.mailbox, "schedule_enabled", False):
            raise SmartMailError(
                "Native scheduling capability is not enabled for this adapter; "
                "use --enable-extension-schedule during controlled live acceptance")
        request = self._schedule_request(preparation, execution)
        attempt_id = self._start_attempt(confirmation, request)
        files, cleanup = self._materialize_attachments(preparation["id"])
        try:
            evidence = self.mailbox.schedule_confirmed(
                request, files, confirmation_id=confirmation["id"], attempt_id=attempt_id)
        except MailboxCapabilityError as error:
            raise SmartMailError(str(error)) from error
        finally:
            cleanup()
        observed_at = self._now()
        state = evidence.get("outcome")
        record = dict(evidence)
        record["outcome_observed_at"] = observed_at
        interruption = None
        if state == "authentication_required":
            interruption = "authentication_required"
            record["interruption"] = interruption
            state = "unknown"
        self._db.execute(
            "UPDATE execution_attempts SET state = ?, evidence = ?, outcome_observed_at = ?, "
            "updated_at = ? WHERE id = ?",
            ("externally_scheduled" if evidence.get("outcome") == "scheduled" else state,
             json.dumps(record, ensure_ascii=False), observed_at, observed_at, attempt_id))
        self._db.commit()
        schedule_id = None
        if evidence.get("outcome") == "scheduled":
            schedule_id = self._record_external_schedule(
                confirmation, attempt_id, request, evidence, replaces=replaces)
            if replaces:
                self._db.execute(
                    "UPDATE external_schedules SET state = 'replaced', updated_at = ? WHERE id = ?",
                    (observed_at, replaces["id"]))
        else:
            self._pause_flow(campaign_id, interruption or (
                "unknown_outcome" if state == "unknown" else "execution_failed"), record)
        self._db.commit()
        return {"attempt": self.get_execution_attempt(attempt_id),
                "schedule": self.get_external_schedule(schedule_id) if schedule_id else None,
                "flow": self._flow_state(campaign_id)}

    def _record_external_schedule(self, confirmation, attempt_id, request, evidence, *,
                                  replaces=None) -> str:
        schedule_id = str(uuid4())
        now = self._now()
        self._db.execute(
            "INSERT INTO external_schedules "
            "(id, confirmation_id, attempt_id, preparation_id, task_id, mailbox_address, "
            "external_id, scheduled_utc, state, evidence, replaces_schedule_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'externally_scheduled', ?, ?, ?, ?)",
            (schedule_id, confirmation["id"], attempt_id, confirmation["preparation_id"],
             confirmation["task_id"], request["sender"].lower(), evidence["external_id"],
             request["scheduled_utc"], json.dumps(evidence, ensure_ascii=False),
             replaces["id"] if replaces else None, now, now))
        self._db.execute(
            "INSERT INTO external_operations "
            "(id, confirmation_id, schedule_id, task_id, kind, state, request, evidence, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, 'schedule_placement', 'done', ?, ?, ?, ?)",
            (str(uuid4()), confirmation["id"], schedule_id, confirmation["task_id"],
             json.dumps(request, ensure_ascii=False), json.dumps(evidence, ensure_ascii=False), now, now))
        return schedule_id

    # ------------------------------------------------------------- queries
    @staticmethod
    def _platform_evidence(schedule) -> dict:
        """Merge the adapter envelope with its platform-specific inner evidence."""
        envelope = schedule["evidence"] if isinstance(schedule, dict) else {}
        envelope = envelope if isinstance(envelope, dict) else {}
        inner = envelope.get("evidence")
        merged = dict(envelope)
        if isinstance(inner, dict):
            for key, value in inner.items():
                merged.setdefault(key, value)
        return merged

    def _schedule_row(self, schedule_id: str):
        row = self._db.execute("SELECT * FROM external_schedules WHERE id = ?",
                               (schedule_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"External schedule not found: {schedule_id}")
        return row

    def get_external_schedule(self, schedule_id: str) -> dict:
        row = self._schedule_row(schedule_id)
        return {
            "id": row["id"], "confirmation_id": row["confirmation_id"],
            "attempt_id": row["attempt_id"], "preparation_id": row["preparation_id"],
            "task_id": row["task_id"], "mailbox_address": row["mailbox_address"],
            "external_id": row["external_id"], "scheduled_utc": row["scheduled_utc"],
            "state": row["state"], "replaces_schedule_id": row["replaces_schedule_id"],
            "evidence": json.loads(row["evidence"] or "{}"),
            "created_at": row["created_at"], "updated_at": row["updated_at"],
        }

    def list_external_schedules(self, *, campaign_id: str | None = None,
                                task_id: str | None = None, state: str | None = None) -> list[dict]:
        sql = ("SELECT s.id FROM external_schedules s "
               "JOIN tasks t ON t.id = s.task_id WHERE 1=1")
        args = []
        if campaign_id:
            sql += " AND t.campaign_id = ?"; args.append(campaign_id)
        if task_id:
            sql += " AND s.task_id = ?"; args.append(task_id)
        if state:
            sql += " AND s.state = ?"; args.append(state)
        sql += " ORDER BY s.rowid"
        return [self.get_external_schedule(row["id"]) for row in self._db.execute(sql, args)]

    # ------------------------------------------------------------ cancellation
    def review_schedule_cancellation(self, schedule_id: str) -> dict:
        """Everything the operator inspects before authorizing external removal."""
        schedule = self.get_external_schedule(schedule_id)
        return {"schedule": schedule,
                "operation": "cancellation",
                "requires_explicit_confirmation": True,
                "note": "Removal is observed before Cancellation is recorded; uncertain removal pauses"}

    def _external_op_confirmation(self, *, kind: str, preparation_id: str, task_id: str,
                                  detail: dict, digest: str) -> dict:
        confirmation_id = str(uuid4())
        now = self._now()
        self._db.execute(
            "INSERT INTO confirmations "
            "(id, preparation_id, task_id, execution_kind, execution_detail, "
            "content_digest, attachments_digest, status, invalidated_reason, confirmed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', '', ?)",
            (confirmation_id, preparation_id, task_id, kind,
             json.dumps(detail, ensure_ascii=False), digest, digest, now))
        return self.get_confirmation(confirmation_id)

    @staticmethod
    def _digest(request: dict) -> str:
        canonical = json.dumps(request, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def confirm_schedule_cancellation(self, schedule_id: str) -> dict:
        """Bind an explicit Cancellation Confirmation to one observed external schedule."""
        schedule = self.get_external_schedule(schedule_id)
        if schedule["state"] == "sent":
            raise SmartMailError("The message was already Sent; Cancellation cannot prevent it")
        if schedule["state"] not in CANCELLABLE_STATES:
            raise SmartMailError(
                f"Cancellation requires an externally scheduled draft; current state is "
                f"{schedule['state']}")
        request = self._cancel_request(schedule)
        detail = {"kind": "cancellation", "schedule_id": schedule_id,
                  "external_id": schedule["external_id"], "request": request}
        with self._db:
            confirmation = self._external_op_confirmation(
                kind="cancellation", preparation_id=schedule["preparation_id"],
                task_id=schedule["task_id"], detail=detail, digest=self._digest(request))
        return {"confirmation": confirmation, "schedule": schedule, "request": request}

    def _cancel_request(self, schedule: dict) -> dict:
        evidence = self._platform_evidence(schedule)
        return {"kind": "cancel_schedule", "sender": schedule["mailbox_address"],
                "external_id": schedule["external_id"],
                "recipient": (evidence.get("recipient") or "").lower(),
                "subject": evidence.get("subject", ""),
                "scheduled_epoch_ms": int(datetime.fromisoformat(
                    schedule["scheduled_utc"]).timestamp() * 1000)}

    def run_schedule_cancellation(self, confirmation_id: str) -> dict:
        confirmation = self.get_confirmation(confirmation_id)
        detail = confirmation["execution"]
        if detail.get("kind") != "cancellation":
            raise SmartMailError("Confirmation is not a Cancellation Confirmation")
        schedule = self.get_external_schedule(detail["schedule_id"])
        request = detail["request"]
        campaign_id = self._campaign_of_task(confirmation["task_id"])
        if self._flow_state(campaign_id)["state"] == "paused":
            raise SmartMailError("Resolve the paused Execution Flow before Cancellation")
        attempt_id = self._start_attempt(confirmation, request)
        if not hasattr(self.mailbox, "cancel_schedule_confirmed"):
            raise SmartMailError("This adapter cannot cancel external schedules")
        try:
            evidence = self.mailbox.cancel_schedule_confirmed(
                request, confirmation_id=confirmation["id"], attempt_id=attempt_id)
        except MailboxCapabilityError as error:
            raise SmartMailError(str(error)) from error
        now = self._now()
        outcome = evidence.get("outcome")
        record = {**evidence, "outcome_observed_at": now}
        op_state = "done"
        with self._db:
            if outcome == "removed" or outcome == "already_cancelled":
                schedule_state = "cancelled"
                attempt_state = "cancelled"
                self._db.execute(
                    "UPDATE confirmations SET status = 'consumed' WHERE id = ?",
                    (confirmation["id"],))
            elif outcome == "already_sent":
                schedule_state = "sent"
                attempt_state = "sent"
                self._freeze_scheduled_sent(schedule, attempt_id, confirmation, evidence)
                self._db.execute(
                    "UPDATE confirmations SET status = 'consumed' WHERE id = ?",
                    (confirmation["id"],))
                self._pause_flow(campaign_id, "schedule_sent_during_cancel", {
                    "detail": "The message Sent before Cancellation; its Sent Record is frozen and "
                              "the pending cancellation did not prevent sending",
                    "schedule_id": schedule["id"]})
            elif outcome == "authentication_required":
                schedule_state = schedule["state"]
                attempt_state = "unknown"
                record["interruption"] = "authentication_required"
                self._pause_flow(campaign_id, "authentication_required", record)
            else:
                schedule_state = "cancel_unknown" if outcome != "failed" else schedule["state"]
                attempt_state = "unknown" if outcome != "failed" else "failed"
                self._pause_flow(campaign_id,
                                 "unknown_outcome" if attempt_state == "unknown" else "execution_failed",
                                 record)
            prior_evidence = schedule["evidence"] if isinstance(schedule["evidence"], dict) else {}
            self._db.execute(
                "UPDATE external_schedules SET state = ?, evidence = ?, updated_at = ? WHERE id = ?",
                (schedule_state, json.dumps({**prior_evidence, "cancellation": evidence},
                                             ensure_ascii=False),
                 now, schedule["id"]))
            self._db.execute(
                "UPDATE execution_attempts SET state = ?, evidence = ?, outcome_observed_at = ?, "
                "updated_at = ? WHERE id = ?",
                (attempt_state, json.dumps(record, ensure_ascii=False), now, now, attempt_id))
            self._db.execute(
                "INSERT INTO external_operations "
                "(id, confirmation_id, schedule_id, task_id, kind, state, request, evidence, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, 'cancellation', ?, ?, ?, ?, ?)",
                (str(uuid4()), confirmation["id"], schedule["id"], confirmation["task_id"],
                 op_state, json.dumps(request, ensure_ascii=False),
                 json.dumps(evidence, ensure_ascii=False), now, now))
        return {"attempt": self.get_execution_attempt(attempt_id),
                "schedule": self.get_external_schedule(schedule["id"]),
                "flow": self._flow_state(campaign_id)}

    def _freeze_scheduled_sent(self, schedule: dict, attempt_id: str,
                               confirmation: dict, evidence: dict) -> str:
        """Create the immutable Sent Record when evidence proves a schedule fired."""
        attempt = self.get_execution_attempt(attempt_id)
        request = {key: attempt["request"].get(key) for key in
                   ("sender", "recipient", "subject", "body")}
        request["sender"] = schedule["mailbox_address"]
        sent_evidence = {**evidence, "outcome": "sent", "reference": schedule["external_id"],
                         "frozen_from_schedule": True}
        sent_id = self._record_sent(confirmation, attempt_id, request, sent_evidence)
        self._db.execute(
            "UPDATE follow_up_actions SET status = 'sent' WHERE preparation_id = ?",
            (schedule["preparation_id"],))
        return sent_id

    # ------------------------------------------------------------- replacement
    def confirm_schedule_replacement(self, schedule_id: str,
                                     replacement_confirmation_id: str) -> dict:
        """Confirm removal of an external schedule followed by a new confirmed submission.

        The prior Confirmation does not transfer: the replacement carries its own
        active scheduled Confirmation, and this binds the exact sequencing.
        """
        schedule = self.get_external_schedule(schedule_id)
        if schedule["state"] not in CANCELLABLE_STATES:
            raise SmartMailError(
                f"Replacement requires an externally scheduled draft; state is {schedule['state']}")
        replacement = self.get_confirmation(replacement_confirmation_id)
        if replacement["status"] != "active" or replacement["execution"].get("kind") != "scheduled":
            raise SmartMailError(
                "The replacement needs its own active scheduled Confirmation bound to an exact time")
        if replacement["preparation_id"] == schedule["preparation_id"]:
            raise SmartMailError(
                "A Scheduled Replacement needs a fresh Preparation (Rewrite); Confirmation does not transfer")
        new_preparation = self.get_preparation(replacement["preparation_id"])
        if new_preparation["status"] != "active" or new_preparation["superseded_by"]:
            raise SmartMailError("The replacement Preparation is not active")
        request = {**self._cancel_request(schedule), "kind": "cancel_schedule"}
        detail = {"kind": "replacement", "schedule_id": schedule_id,
                  "external_id": schedule["external_id"],
                  "replacement_confirmation_id": replacement_confirmation_id,
                  "replacement_preparation_id": replacement["preparation_id"],
                  "removal_request": request}
        digest = self._digest({"remove": request,
                               "replacement_confirmation_id": replacement_confirmation_id})
        with self._db:
            confirmation = self._external_op_confirmation(
                kind="replacement", preparation_id=replacement["preparation_id"],
                task_id=replacement["task_id"], detail=detail, digest=digest)
        return {"confirmation": confirmation, "schedule": schedule,
                "replacement_confirmation": replacement}

    def run_schedule_replacement(self, confirmation_id: str) -> dict:
        """Verify removal before submitting the replacement; never auto-restore."""
        confirmation = self.get_confirmation(confirmation_id)
        detail = confirmation["execution"]
        if detail.get("kind") != "replacement":
            raise SmartMailError("Confirmation is not a Scheduled Replacement Confirmation")
        schedule = self.get_external_schedule(detail["schedule_id"])
        replacement = self.get_confirmation(detail["replacement_confirmation_id"])
        campaign_id = self._campaign_of_task(confirmation["task_id"])
        now = self._now()
        removal_request = detail["removal_request"]
        # Phase 1: the replacement Confirmation authorizes removal of the exact bound identity.
        removal_attempt = self._start_attempt(confirmation, removal_request)
        evidence = self.mailbox.cancel_schedule_confirmed(
            removal_request, confirmation_id=confirmation["id"], attempt_id=removal_attempt)
        outcome = evidence.get("outcome")
        with self._db:
            self._db.execute(
                "UPDATE execution_attempts SET state = ?, evidence = ?, outcome_observed_at = ?, "
                "updated_at = ? WHERE id = ?",
                (outcome, json.dumps(evidence, ensure_ascii=False), now, now, removal_attempt))
            self._db.execute(
                "INSERT INTO external_operations "
                "(id, confirmation_id, schedule_id, task_id, kind, state, request, evidence, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, 'replacement', ?, ?, ?, ?, ?)",
                (str(uuid4()), confirmation["id"], schedule["id"], confirmation["task_id"],
                 "done" if outcome in ("removed", "already_cancelled") else "unknown",
                 json.dumps({"phase": "removal", "request": removal_request}, ensure_ascii=False),
                 json.dumps(evidence, ensure_ascii=False), now, now))
        if outcome == "already_sent":
            self._freeze_scheduled_sent(schedule, removal_attempt, confirmation, evidence)
            with self._db:
                self._db.execute(
                    "UPDATE external_schedules SET state = 'sent', updated_at = ? WHERE id = ?",
                    (now, schedule["id"]))
                self._db.execute(
                    "UPDATE confirmations SET status = 'invalidated', invalidated_reason = "
                    "'original_sent_during_replacement' WHERE id = ?", (confirmation["id"],))
                self._pause_flow(campaign_id, "schedule_sent_during_replacement", {
                    "detail": "The original Sent during replacement; a new linked action and "
                              "Confirmation is required for further communication",
                    "schedule_id": schedule["id"]})
            return {"phase": "original_sent", "replacement_placed": False,
                    "removal_attempt": self.get_execution_attempt(removal_attempt),
                    "flow": self._flow_state(campaign_id)}
        if outcome not in ("removed", "already_cancelled"):
            with self._db:
                self._db.execute(
                    "UPDATE external_schedules SET state = 'cancel_unknown', updated_at = ? WHERE id = ?",
                    (now, schedule["id"]))
                self._db.execute(
                    "UPDATE confirmations SET status = 'invalidated', invalidated_reason = "
                    "'removal_unverified' WHERE id = ?", (confirmation["id"],))
                self._pause_flow(campaign_id, "unknown_outcome", {
                    "detail": "Removal could not be verified; replacement is not submitted",
                    "schedule_id": schedule["id"]})
            return {"phase": "removal_unverified", "replacement_placed": False,
                    "removal_attempt": self.get_execution_attempt(removal_attempt),
                    "flow": self._flow_state(campaign_id)}
        # Removal was observed: record the original as removed before any new work.
        # A later replacement failure never restores it.
        with self._db:
            prior_evidence = schedule["evidence"] if isinstance(schedule["evidence"], dict) else {}
            self._db.execute(
                "UPDATE external_schedules SET state = 'cancelled', "
                "evidence = ?, updated_at = ? WHERE id = ?",
                (json.dumps({**prior_evidence, "cancelled_by": "scheduled_replacement",
                              "replacement_confirmation_id": replacement["id"]}, ensure_ascii=False),
                 now, schedule["id"]))
        # Phase 2: place the replacement. A failure never restores the original.
        placement = self._place_schedule_attempt(replacement, replaces=schedule)
        placed = placement.get("schedule") is not None
        with self._db:
            self._db.execute(
                "UPDATE confirmations SET status = ? WHERE id = ?",
                ("consumed" if placed else "invalidated", confirmation["id"]))
            self._db.execute(
                "INSERT INTO external_operations "
                "(id, confirmation_id, schedule_id, task_id, kind, state, request, evidence, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, 'replacement', ?, ?, ?, ?, ?)",
                (str(uuid4()), confirmation["id"], schedule["id"], confirmation["task_id"],
                 "done" if placed else "unknown",
                 json.dumps({"phase": "placement", "replacement_confirmation_id": replacement["id"]},
                            ensure_ascii=False),
                 json.dumps({"placement_attempt": placement["attempt"]["id"]}, ensure_ascii=False),
                 now, self._now()))
        return {"phase": "complete" if placed else "replacement_submission_unknown",
                "replacement_placed": placed,
                "removal_attempt": self.get_execution_attempt(removal_attempt),
                "placement": placement, "flow": placement["flow"]}

    # ------------------------------------------------------------------ recall
    def review_recall(self, sent_record_id: str) -> dict:
        record = self.get_sent_record(sent_record_id)
        eligibility = {"platform_support": False, "message_recallable": None,
                       "basis": "Recall eligibility requires full-letter evidence; the metadata-only "
                                "extension observation cannot establish it"}
        observation = self._db.execute(
            "SELECT m.evidence FROM mailbox_message_observations m "
            "JOIN mailbox_observation_runs r ON r.id = m.run_id "
            "WHERE m.platform_reference = ? ORDER BY r.rowid DESC LIMIT 1",
            (record["reference"],)).fetchone()
        if observation:
            evidence = json.loads(observation["evidence"])
            detail = evidence.get("list") or evidence.get("detail") or {}
            if "recallable" in detail:
                eligibility = {"platform_support": True,
                               "message_recallable": bool(detail["recallable"]),
                               "basis": "Observed full-letter recallable flag"}
        return {"sent_record": record, "eligibility": eligibility,
                "requires_explicit_confirmation": True,
                "note": "Recall outcome is recorded separately and never blocks completion"}

    def confirm_recall(self, sent_record_id: str) -> dict:
        record = self.get_sent_record(sent_record_id)
        review = self.review_recall(sent_record_id)
        if review["eligibility"]["message_recallable"] is False:
            raise SmartMailError("Platform evidence says this message is not eligible for Recall")
        request = {"kind": "recall", "sender": record["sender"],
                   "external_id": record["reference"],
                   "recipient": record["recipient"], "subject": record["subject"]}
        detail = {"kind": "recall", "sent_record_id": sent_record_id,
                  "external_id": record["reference"], "request": request}
        with self._db:
            confirmation = self._external_op_confirmation(
                kind="recall", preparation_id=record["preparation_id"],
                task_id=record["task_id"], detail=detail, digest=self._digest(request))
        return {"confirmation": confirmation, "sent_record_id": sent_record_id, "request": request}

    def run_recall(self, confirmation_id: str) -> dict:
        confirmation = self.get_confirmation(confirmation_id)
        detail = confirmation["execution"]
        if detail.get("kind") != "recall":
            raise SmartMailError("Confirmation is not a Recall Confirmation")
        request = detail["request"]
        attempt_id = self._start_attempt(confirmation, request)
        now = self._now()
        if not hasattr(self.mailbox, "recall_confirmed"):
            raise SmartMailError("This adapter cannot Recall messages")
        try:
            evidence = self.mailbox.recall_confirmed(
                request, confirmation_id=confirmation["id"], attempt_id=attempt_id)
        except MailboxCapabilityError as error:
            raise SmartMailError(str(error)) from error
        # Recall is never a completion blocker: record the observed outcome and continue.
        with self._db:
            self._db.execute(
                "UPDATE execution_attempts SET state = 'done', evidence = ?, "
                "outcome_observed_at = ?, updated_at = ? WHERE id = ?",
                (json.dumps(evidence, ensure_ascii=False), now, now, attempt_id))
            self._db.execute(
                "INSERT INTO external_operations "
                "(id, confirmation_id, schedule_id, task_id, kind, state, request, evidence, "
                "created_at, updated_at) VALUES (?, ?, NULL, ?, 'recall', 'done', ?, ?, ?, ?)",
                (str(uuid4()), confirmation["id"], confirmation["task_id"],
                 json.dumps(request, ensure_ascii=False),
                 json.dumps(evidence, ensure_ascii=False), now, now))
            self._db.execute(
                "UPDATE confirmations SET status = 'consumed' WHERE id = ?", (confirmation["id"],))
        return {"attempt": self.get_execution_attempt(attempt_id),
                "recall_outcome": evidence.get("outcome"),
                "blocks_completion": False}

    # -------------------------------------------------- direct mailbox changes
    def configure_observation(self, student_id: str, interval_seconds: int) -> dict:
        """Store observation-only periodicity; it grants no external authority."""
        mailbox = self._mailbox_for_student(student_id)
        if not isinstance(interval_seconds, int) or interval_seconds < 0:
            raise SmartMailError("Observation interval must be a non-negative integer of seconds")
        now = self._now()
        with self._db:
            self._db.execute(
                "INSERT INTO mailbox_settings (mailbox_id, observation_interval_seconds, updated_at) "
                "VALUES (?, ?, ?) ON CONFLICT(mailbox_id) DO UPDATE SET "
                "observation_interval_seconds = excluded.observation_interval_seconds, "
                "updated_at = excluded.updated_at", (mailbox["id"], interval_seconds, now))
        return {"mailbox_id": mailbox["id"], "observation_interval_seconds": interval_seconds,
                "authority": "observation_only; periodic observation never alters external sending state"}

    def get_observation_settings(self, student_id: str) -> dict:
        mailbox = self._mailbox_for_student(student_id)
        row = self._db.execute("SELECT * FROM mailbox_settings WHERE mailbox_id = ?",
                               (mailbox["id"],)).fetchone()
        return {"student_id": student_id, "mailbox_id": mailbox["id"],
                "observation_interval_seconds": row["observation_interval_seconds"] if row else 0}

    def reconcile_external_schedules(self, student_id: str) -> dict:
        """Observe mailbox evidence and reconcile every tracked schedule without restoring plans."""
        refreshed = self.refresh_mailbox(student_id)
        mailbox = self._mailbox_for_student(student_id)
        findings = self._reconcile_external_schedules(
            mailbox, refreshed["reconciliation"]["id"], refreshed["observation"]["observed_at"])
        return {"observation": refreshed["observation"],
                "reconciliation": refreshed["reconciliation"], "schedule_findings": findings}

    def _reconcile_external_schedules(self, mailbox: dict, reconciliation_id: str,
                                      observed_at: str) -> list[dict]:
        """Compare tracked commitments against observed scheduled/sent rows.

        Time elapsing alone never establishes Sent; external edits never inherit
        Confirmation and never restore old content or schedules.
        """
        messages = list(self._db.execute(
            "SELECT * FROM mailbox_message_observations WHERE run_id = "
            "(SELECT id FROM mailbox_observation_runs WHERE mailbox_id = ? "
            "ORDER BY rowid DESC LIMIT 1)", (mailbox["id"],)))
        by_reference = {m["platform_reference"]: m for m in messages if m["platform_reference"]}
        results = []
        schedules = self.list_external_schedules()
        for schedule in schedules:
            if schedule["mailbox_address"] != mailbox["address"]:
                continue
            result = self._reconcile_one_schedule(schedule, by_reference, reconciliation_id, observed_at)
            if result:
                results.append(result)
        # Untracked external scheduled drafts are already recorded by the regular
        # reconciliation pass as observed_external_schedule: distinct from local
        # plans, never inheriting Confirmation, never restored, never evidence of Sent.
        return results

    def _reconcile_one_schedule(self, schedule, by_reference, reconciliation_id, observed_at) -> dict:
        platform = self._platform_evidence(schedule)
        message = by_reference.get(schedule["external_id"])
        now = self._now()
        # Identity may appear after the fact without a composite id; fall back to exact content.
        if message is None:
            candidates = [m for m in by_reference.values()
                          if m["subject"] == platform.get("subject")
                          and m["counterpart"].lower() == (platform.get("recipient") or "").lower()]
            message = candidates[0] if len(candidates) == 1 else None
        if message is None:
            if schedule["state"] in ACTIVE_SCHEDULE_STATES:
                self._insert_reconciliation_finding(
                    reconciliation_id, None, "schedule_evidence_missing",
                    "external_schedule", schedule["id"], basis="manual_refresh",
                    detail="No current external evidence; the schedule remains tracked, never Sent by elapsed time")
            return {"schedule_id": schedule["id"], "state": schedule["state"], "finding": "no_change"}
        if message["status"] == "scheduled":
            observed_time = message["observed_time"]
            prior = platform.get("scheduled_beijing")
            discrepancy = bool(prior and observed_time and prior not in observed_time
                               and observed_time not in prior)
            if schedule["state"] == "placement_unknown":
                with self._db:
                    self._db.execute(
                        "UPDATE external_schedules SET state = 'externally_scheduled', "
                        "external_id = ?, evidence = ?, updated_at = ? WHERE id = ?",
                        (message["platform_reference"],
                         json.dumps({**schedule["evidence"], "reconciled_from_observation": True,
                                     "scheduled_beijing": observed_time}, ensure_ascii=False),
                         now, schedule["id"]))
            elif discrepancy:
                self._insert_reconciliation_finding(
                    reconciliation_id, message["id"], "external_schedule_changed",
                    "external_schedule", schedule["id"], basis="platform_reference",
                    detail=f"Observed schedule time {observed_time} differs from the confirmed time {prior}")
                self._pause_flow(self._campaign_of_task(schedule["task_id"]),
                                 "external_schedule_changed",
                                 {"detail": "External schedule was edited directly; local plans are not restored",
                                  "schedule_id": schedule["id"]})
            else:
                self._insert_reconciliation_finding(
                    reconciliation_id, message["id"], "external_schedule_still_active",
                    "external_schedule", schedule["id"], basis="platform_reference")
            return {"schedule_id": schedule["id"], "state": "externally_scheduled",
                    "finding": "external_schedule_changed" if discrepancy else "still_active"}
        if message["status"] == "sent" and schedule["state"] in ACTIVE_SCHEDULE_STATES | {"cancelled", "cancel_unknown"}:
            # The mailbox executed the commitment; freeze the immutable Sent Record.
            attempt = self.get_execution_attempt(schedule["attempt_id"])
            confirmation = self.get_confirmation(schedule["confirmation_id"])
            evidence = {"outcome": "sent", "reference": message["platform_reference"],
                        "reconciled": True, "reconciliation_id": reconciliation_id,
                        "mailbox_observation_id": message["id"], "frozen_from_schedule": True,
                        "external_id": schedule["external_id"],
                        "recipient": message["counterpart"], "subject": message["subject"]}
            with self._db:
                self._record_sent(confirmation, attempt["id"], attempt["request"], evidence)
                self._db.execute(
                    "UPDATE execution_attempts SET state = 'sent', evidence = ?, "
                    "phase = 'recorded', outcome_observed_at = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(evidence, ensure_ascii=False), observed_at, now, attempt["id"]))
                self._db.execute(
                    "UPDATE external_schedules SET state = 'sent', updated_at = ? WHERE id = ?",
                    (now, schedule["id"]))
                self._db.execute(
                    "UPDATE confirmations SET status = 'consumed' WHERE id = ? AND status = 'active'",
                    (confirmation["id"],))
            self._insert_reconciliation_finding(
                reconciliation_id, message["id"], "schedule_observed_sent",
                "external_schedule", schedule["id"], basis="platform_reference",
                detail="Observed Sent evidence froze the Sent Record")
            return {"schedule_id": schedule["id"], "state": "sent", "finding": "observed_sent"}
        return {"schedule_id": schedule["id"], "state": schedule["state"], "finding": "no_change"}
