"""Execution Flow pauses, restart recovery and explicit Manual Takeover."""

import json

from ..errors import SmartMailError


class RecoveryOperations:
    """Execution Flow pauses, restart recovery and explicit Manual Takeover."""

    def _recover_unfinished_execution(self) -> None:
        """Turn a process-boundary interruption into an explicit Unknown Outcome.

        An attempt persisted as ``in_progress`` may have crossed the mailbox
        boundary even when the local process did not get an adapter response.
        It is therefore never retried automatically after restart.  The
        operator must reconcile mailbox evidence before continuing.
        """
        rows = list(self._db.execute(
            "SELECT a.*, t.campaign_id FROM execution_attempts a "
            "JOIN tasks t ON t.id = a.task_id "
            "WHERE a.state IN ('in_progress', 'sent') ORDER BY a.rowid"))
        if not rows:
            # No attempt was left open, but a run may still have been: close it from
            # the outcomes its items already carry rather than leaving it running.
            self._reconcile_running_runs()
            return
        recovered_at = self._now()
        for row in rows:
            if row["state"] == "sent":
                existing_sent = self._db.execute(
                    "SELECT id FROM sent_records WHERE attempt_id = ?", (row["id"],)).fetchone()
                if existing_sent:
                    self._db.execute(
                        "UPDATE confirmations SET status = 'consumed' WHERE id = ? "
                        "AND status = 'active'", (row["confirmation_id"],))
                    evidence = json.loads(row["evidence"]) if row["evidence"] else {}
                    evidence.update({
                        "phase": "recorded",
                        "recovered_sent_record": True,
                        "sent_record_id": existing_sent["id"],
                    })
                    self._db.execute(
                        "UPDATE execution_attempts SET evidence = ?, phase = 'recorded', "
                        "updated_at = ? WHERE id = ?",
                        (json.dumps(evidence, ensure_ascii=False), recovered_at, row["id"]))
                    continue
                evidence = json.loads(row["evidence"]) if row["evidence"] else {}
                request = json.loads(row["request"])
                try:
                    confirmation = self.get_confirmation(row["confirmation_id"])
                    self._record_sent(confirmation, row["id"], request, evidence)
                    self._db.execute(
                        "UPDATE confirmations SET status = 'consumed' WHERE id = ? "
                        "AND status = 'active'", (row["confirmation_id"],))
                    evidence["phase"] = "recorded"
                    evidence["recovered_sent_record"] = True
                    self._db.execute(
                        "UPDATE execution_attempts SET evidence = ?, phase = 'recorded', "
                        "updated_at = ? WHERE id = ?",
                        (json.dumps(evidence, ensure_ascii=False), recovered_at, row["id"]))
                except Exception as error:
                    evidence.update({
                        "phase": "recovery_required",
                        "recovered_after_restart": True,
                        "detail": str(error) or "Sent Record recovery failed",
                    })
                    self._db.execute(
                        "UPDATE execution_attempts SET evidence = ?, phase = 'recovery_required', "
                        "updated_at = ? WHERE id = ?",
                        (json.dumps(evidence, ensure_ascii=False), recovered_at, row["id"]))
                    self._pause_flow_if_idle(row["campaign_id"], "recovery_required", evidence)
                continue
            evidence = json.loads(row["evidence"]) if row["evidence"] else {}
            evidence.update({
                "outcome": "unknown",
                "recovered_after_restart": True,
                "recovered_at": recovered_at,
                "phase": "recovery_required",
                "detail": (
                    "The process stopped while external submission was in progress; "
                    "reconcile mailbox evidence before continuing"
                ),
            })
            self._db.execute(
                "UPDATE execution_attempts SET state = 'unknown', evidence = ?, "
                "phase = 'recovery_required', outcome_observed_at = ?, updated_at = ? "
                "WHERE id = ?",
                (json.dumps(evidence, ensure_ascii=False), recovered_at, recovered_at, row["id"]))
            self._pause_flow_if_idle(
                row["campaign_id"], "recovery_required", evidence)
        self._db.commit()
        # Attempt outcomes are re-established first; a run left open by the restart
        # is then closed from those outcomes rather than assumed to have finished.
        self._reconcile_running_runs()

    def reconcile_and_continue(self, attempt_id: str,
                               confirmation_ids: list[str] | None = None,
                               *, acknowledge: bool = False) -> dict:
        """Observe a manual or interrupted action before resolving or continuing it.

        An operator acknowledgment is deliberately not treated as evidence of
        sending.  Only a mailbox observation with an outbound ``sent`` state
        can resolve the attempt and create its immutable Sent Record.
        """
        row = self._db.execute(
            "SELECT * FROM execution_attempts WHERE id = ?", (attempt_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Execution Attempt not found: {attempt_id}")
        if row["state"] not in ("in_progress", "unknown"):
            raise SmartMailError(
                f"Execution Attempt cannot be reconciled from state {row['state']}")
        task = self.get_task(row["task_id"])
        refreshed = self.refresh_mailbox(task["student_id"])
        resolved = self._resolve_attempt_from_observation(attempt_id, refreshed)
        if not resolved:
            # Keep the attempt unresolved even when the operator explicitly
            # acknowledges the manual step.  The acknowledgment is inspectable
            # evidence, never a substitute for mailbox confirmation.
            if acknowledge:
                evidence = json.loads(row["evidence"]) if row["evidence"] else {}
                evidence["operator_acknowledged"] = True
                self._db.execute(
                    "UPDATE execution_attempts SET evidence = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(evidence, ensure_ascii=False), self._now(), attempt_id))
                self._db.commit()
            self._pause_flow_if_idle(
                task["campaign_id"], "reconcile_required",
                {"detail": "Mailbox evidence did not establish that the action was Sent"})
            self._db.commit()
        continued = None
        if resolved and confirmation_ids:
            continued = self.run_execution(confirmation_ids)
        return {
            "resolved": resolved,
            "attempt": self.get_execution_attempt(attempt_id),
            "reconciliation": self.get_reconciliation(refreshed["reconciliation"]["id"]),
            "continued": continued,
        }

    def _resolve_attempt_from_observation(self, attempt_id: str, refreshed: dict) -> bool:
        """Resolve one unresolved attempt only from unique mailbox-confirmed Sent evidence."""
        row = self._db.execute(
            "SELECT * FROM execution_attempts WHERE id = ?", (attempt_id,)).fetchone()
        if row is None or row["state"] not in ("in_progress", "unknown"):
            return False
        request = json.loads(row["request"])
        candidates = [message for message in refreshed["observation"]["messages"]
                      if message["direction"] == "outbound"
                      and message["status"] == "sent"
                      and not message["ambiguity"]
                      and self._list_fields_match(message, request)]
        if len(candidates) != 1:
            return False
        message = candidates[0]
        observed_at = self._now()
        evidence = json.loads(row["evidence"]) if row["evidence"] else {}
        evidence.update({
            "outcome": "sent",
            "reference": message["platform_reference"] or evidence.get(
                "reference", f"reconciled-{message['id']}"),
            "reconciled": True,
            "reconciliation_id": refreshed["reconciliation"]["id"],
            "mailbox_observation_id": refreshed["observation"]["id"],
            "outcome_observed_at": observed_at,
            "detail": "Mailbox evidence established Sent after an unresolved attempt",
        })
        with self._db:
            self._db.execute(
                "UPDATE execution_attempts SET state = 'sent', evidence = ?, "
                "phase = 'outcome_observed', outcome_observed_at = ?, updated_at = ? "
                "WHERE id = ?",
                (json.dumps(evidence, ensure_ascii=False), observed_at, observed_at, attempt_id))
            sent = self._db.execute(
                "SELECT id FROM sent_records WHERE attempt_id = ?", (attempt_id,)).fetchone()
            if sent is None:
                confirmation = self.get_confirmation(row["confirmation_id"])
                sent_id = self._record_sent(confirmation, attempt_id, request, evidence)
            else:
                sent_id = sent["id"]
            self._db.execute(
                "UPDATE confirmations SET status = 'consumed' WHERE id = ? "
                "AND status = 'active'", (row["confirmation_id"],))
            evidence["sent_record_id"] = sent_id
            self._db.execute(
                "UPDATE execution_attempts SET evidence = ?, phase = 'recorded', updated_at = ? "
                "WHERE id = ?", (json.dumps(evidence, ensure_ascii=False), self._now(), attempt_id))
            self._note_resolved_attempt(attempt_id, "sent")
            summary_row = self._db.execute(
                "SELECT summary FROM reconciliations WHERE id = ?",
                (refreshed["reconciliation"]["id"],)).fetchone()
            summary = json.loads(summary_row["summary"])
            summary["local_state_changed"] = True
            summary["resolved_execution_attempts"] = summary.get(
                "resolved_execution_attempts", 0) + 1
            self._db.execute(
                "UPDATE reconciliations SET summary = ? WHERE id = ?",
                (json.dumps(summary, ensure_ascii=False), refreshed["reconciliation"]["id"]))
            self._clear_recovery_pause_if_resolved(row["task_id"])
        return True

    def resume_execution(self, campaign_id: str,
                         confirmation_ids: list[str] | None = None) -> dict:
        """Resume only active, still-valid Confirmations after persisted recovery checks."""
        self.get_campaign(campaign_id)
        flow = self._flow_state(campaign_id)
        if flow["state"] == "paused":
            return {"attempts": [], "paused": True, "flow": flow}
        confirmations = (
            [self.get_confirmation(confirmation_id) for confirmation_id in confirmation_ids]
            if confirmation_ids is not None else self.list_confirmations(campaign_id))
        for confirmation in confirmations:
            if self._campaign_of_task(confirmation["task_id"]) != campaign_id:
                raise SmartMailError(
                    f"Confirmation is outside Campaign {campaign_id}: {confirmation['id']}")
            if self._confirmation_expired(confirmation):
                detail = self._expired_detail()
                self._pause_flow(campaign_id, "confirmation_expired", {"detail": detail})
                self._db.commit()
                return {"attempts": [], "paused": True,
                        "flow": self._flow_state(campaign_id),
                        "expired_confirmation_id": confirmation["id"]}
        if not confirmations:
            return {"attempts": [], "paused": False, "flow": flow}
        return self.run_execution([confirmation["id"] for confirmation in confirmations])

    def recover_execution(self, campaign_id: str,
                          confirmation_ids: list[str] | None = None) -> dict:
        """Compatibility name for the operator-facing restart recovery operation."""
        return self.resume_execution(campaign_id, confirmation_ids)

    def execution_status(self, campaign_id: str) -> dict:
        """The current Execution Flow state for a Campaign; absent means idle."""
        self.get_campaign(campaign_id)
        return self._flow_state(campaign_id)

    def stop_execution_attempt(self, attempt_id: str, detail: str = "") -> dict:
        """Stop an unresolved attempt so the Execution Flow can proceed under a fresh decision."""
        row = self._db.execute(
            "SELECT * FROM execution_attempts WHERE id = ?", (attempt_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Execution Attempt not found: {attempt_id}")
        if row["state"] not in ("in_progress", "unknown"):
            raise SmartMailError(
                f"Execution Attempt is not active ({row['state']}); "
                "reconciliation is required before it can be resolved")
        evidence = json.loads(row["evidence"]) if row["evidence"] else {}
        evidence["stopped"] = True
        if detail:
            evidence["detail"] = detail
        with self._db:
            self._db.execute(
                "UPDATE execution_attempts SET state = 'stopped', evidence = ? WHERE id = ?",
                (json.dumps(evidence, ensure_ascii=False), attempt_id))
            campaign_id = self._campaign_of_task(row["task_id"])
            flow = self._flow_state(campaign_id)
            if flow["state"] == "paused" and flow["reason"] in {
                    "unknown_outcome", "recovery_required", "reconcile_required",
                    "manual_takeover", "authentication_required"}:
                self._db.execute(
                    "DELETE FROM execution_flow WHERE campaign_id = ?", (campaign_id,))
        return self.get_execution_attempt(attempt_id)

    def take_over_execution(self, attempt_id: str, detail: str = "") -> dict:
        """Record an explicit Manual Takeover without asserting that it was Sent."""
        row = self._db.execute(
            "SELECT * FROM execution_attempts WHERE id = ?", (attempt_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Execution Attempt not found: {attempt_id}")
        if row["state"] not in ("in_progress", "unknown"):
            raise SmartMailError(
                f"Execution Attempt is not unresolved ({row['state']})")
        evidence = json.loads(row["evidence"]) if row["evidence"] else {}
        evidence["manual_takeover"] = True
        if detail:
            evidence["detail"] = detail
        evidence["phase"] = "manual_takeover"
        now = self._now()
        with self._db:
            self._db.execute(
                "UPDATE execution_attempts SET state = 'unknown', evidence = ?, "
                "phase = 'manual_takeover', updated_at = ? WHERE id = ?",
                (json.dumps(evidence, ensure_ascii=False), now, attempt_id))
            self._pause_flow_if_idle(
                self._campaign_of_task(row["task_id"]), "manual_takeover", evidence)
        return self.get_execution_attempt(attempt_id)

    def manual_takeover(self, attempt_id: str, detail: str = "") -> dict:
        """Alias using the domain noun for an explicit operator takeover."""
        return self.take_over_execution(attempt_id, detail)

    def reconcile_execution(self, attempt_id: str,
                            confirmation_ids: list[str] | None = None,
                            *, acknowledge: bool = False) -> dict:
        """Alias for explicit reconcile-and-continue at the core boundary."""
        return self.reconcile_and_continue(
            attempt_id, confirmation_ids, acknowledge=acknowledge)

    def _flow_state(self, campaign_id: str) -> dict:
        row = self._db.execute(
            "SELECT * FROM execution_flow WHERE campaign_id = ?", (campaign_id,)).fetchone()
        if row is None:
            return {"campaign_id": campaign_id, "state": "idle", "reason": "", "detail": ""}
        return {"campaign_id": campaign_id, "state": row["state"],
                "reason": row["reason"], "detail": row["detail"]}

    def _pause_flow(self, campaign_id: str, reason: str, evidence: dict) -> None:
        detail = evidence.get("detail", "") if isinstance(evidence, dict) else ""
        self._db.execute(
            "INSERT INTO execution_flow VALUES (?, 'paused', ?, ?) "
            "ON CONFLICT(campaign_id) DO UPDATE SET state = 'paused', "
            "reason = excluded.reason, detail = excluded.detail",
            (campaign_id, reason, detail))

    def _pause_flow_if_idle(self, campaign_id: str, reason: str, evidence: dict) -> None:
        """Add a recovery pause without replacing an existing operator blocker."""
        if self._flow_state(campaign_id)["state"] == "idle":
            self._pause_flow(campaign_id, reason, evidence)

    def _clear_recovery_pause_if_resolved(self, task_id: str) -> None:
        """Release only a recovery pause once every unresolved attempt is resolved."""
        campaign_id = self._campaign_of_task(task_id)
        flow = self._flow_state(campaign_id)
        if flow["reason"] not in {
            "recovery_required", "unknown_outcome", "reconcile_required",
                "manual_takeover", "authentication_required"}:
            return
        unresolved = self._db.execute(
            "SELECT 1 FROM execution_attempts a JOIN tasks t ON t.id = a.task_id "
            "WHERE t.campaign_id = ? AND a.state IN ('in_progress', 'unknown') LIMIT 1",
            (campaign_id,)).fetchone()
        if unresolved is None:
            self._db.execute("DELETE FROM execution_flow WHERE campaign_id = ?", (campaign_id,))

    def _clear_confirmation_expired_pause(self, campaign_id: str) -> None:
        flow = self._flow_state(campaign_id)
        if flow["reason"] == "confirmation_expired":
            self._db.execute("DELETE FROM execution_flow WHERE campaign_id = ?", (campaign_id,))
