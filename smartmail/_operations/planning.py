"""Sending Plan configuration, scheduling constraints and batch Confirmation."""

import json
from datetime import datetime, time, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ..errors import SmartMailError


_PLAN_DAY_TOKENS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")

_PLAN_CONSTRAINT_LABELS = {
    "windows": "allowed windows",
    "spacing_minutes": "spacing",
    "daily_limit": "daily limit",
    "institution_pace": "same-institution pacing",
}

#: Deterministic defaults for a Campaign that has not configured a Sending Plan.
PLAN_DEFAULTS = {
    "timezone": "UTC",
    "windows": [{"days": list(_PLAN_DAY_TOKENS[:5]), "start": "09:00", "end": "17:00"}],
    "spacing_minutes": 15,
    "daily_limit": 20,
    "horizon_days": 14,
    "institution_limit": 1,
}


class PlanningOperations:
    """Sending Plan configuration, scheduling constraints and batch Confirmation."""

    def get_plan_configuration(self, campaign_id: str) -> dict:
        """Read the effective rules without changing the Campaign."""
        self.get_campaign(campaign_id)
        return self._plan_configuration(campaign_id)

    def configure_plan(self, campaign_id: str, *, timezone: str | None = None,
                       windows=None, spacing_minutes: int | None = None,
                       daily_limit: int | None = None,
                       horizon_days: int | None = None,
                       institution_limit: int | None = None) -> dict:
        """Configure the allowed windows, timezone, spacing, limits and institution pacing.

        Only the supplied fields change; an unconfigured Campaign starts from the
        deterministic defaults, so a proposal can always be reproduced.
        """
        self.get_campaign(campaign_id)
        current = self._plan_configuration(campaign_id)
        candidate = {
            "timezone": current["timezone"] if timezone is None
            else self._plan_timezone(timezone),
            "windows": current["windows"] if windows is None else self._plan_windows(windows),
            "spacing_minutes": current["spacing_minutes"] if spacing_minutes is None
            else self._plan_positive(spacing_minutes, "spacing", "minutes between actions"),
            "daily_limit": current["daily_limit"] if daily_limit is None
            else self._plan_positive(daily_limit, "daily limit", "actions per day"),
            "horizon_days": current["horizon_days"] if horizon_days is None
            else self._plan_positive(horizon_days, "planning horizon", "days to search"),
            "institution_limit": current["institution_limit"] if institution_limit is None
            else self._plan_positive(
                institution_limit, "institution limit", "advisors per institution per session"),
        }
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO plan_configurations "
                "(campaign_id, timezone, windows, spacing_minutes, daily_limit, horizon_days, "
                "institution_limit) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (campaign_id, candidate["timezone"],
                 json.dumps(candidate["windows"], ensure_ascii=False),
                 candidate["spacing_minutes"], candidate["daily_limit"],
                 candidate["horizon_days"], candidate["institution_limit"]))
        return self._plan_configuration(campaign_id)

    def _plan_configuration(self, campaign_id: str) -> dict:
        """The Campaign's configuration, falling back to the deterministic defaults."""
        row = self._db.execute(
            "SELECT * FROM plan_configurations WHERE campaign_id = ?", (campaign_id,)).fetchone()
        if row is None:
            return {"campaign_id": campaign_id, **{key: (
                list(value) if key == "windows" else value
            ) for key, value in PLAN_DEFAULTS.items()}}
        return {
            "campaign_id": row["campaign_id"], "timezone": row["timezone"],
            "windows": json.loads(row["windows"]),
            "spacing_minutes": row["spacing_minutes"],
            "daily_limit": row["daily_limit"], "horizon_days": row["horizon_days"],
            "institution_limit": row["institution_limit"]
            if "institution_limit" in row.keys() else PLAN_DEFAULTS["institution_limit"],
        }

    @staticmethod
    def _plan_timezone(name) -> str:
        name = str(name).strip()
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError, TypeError) as error:
            raise SmartMailError(
                f"Unknown timezone: {name or '(empty)'}; use an IANA name such as "
                "Asia/Shanghai") from error
        return name

    @staticmethod
    def _plan_positive(value, label: str, unit: str) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError) as error:
            raise SmartMailError(f"A positive integer {label} is required ({unit})") from error
        if number < 1:
            raise SmartMailError(f"A positive integer {label} is required ({unit})")
        return number

    @classmethod
    def _plan_windows(cls, specifications) -> list[dict]:
        if isinstance(specifications, (str, dict)):
            specifications = [specifications]
        if not specifications:
            raise SmartMailError(
                "At least one allowed window is required, for example 'MON-FRI 09:00-17:00'")
        return [cls._plan_window(specification) for specification in specifications]

    @classmethod
    def _plan_window(cls, specification) -> dict:
        if isinstance(specification, dict):
            specification = dict(specification)
            days = specification.pop("days", None)
            start, end = specification.pop("start", ""), specification.pop("end", "")
            if specification or days is None:
                raise SmartMailError(
                    f"Unsupported window {specification}: use "
                    "{'days': ['MON'], 'start': '09:00', 'end': '17:00'}")
        else:
            tokens = str(specification).split()
            if len(tokens) < 2:
                raise SmartMailError(
                    f"Unsupported window {specification}: use '<DAYS> HH:MM-HH:MM'")
            days, start, end = tokens[:-1], "", tokens[-1]
            start, separator, end = end.partition("-")
            if not separator:
                raise SmartMailError(
                    f"Unsupported window {specification}: use '<DAYS> HH:MM-HH:MM'")
        window_days = cls._plan_days(days, specification)
        opens = cls._plan_time(start, specification)
        closes = cls._plan_time(end, specification)
        if closes <= opens:
            raise SmartMailError(
                f"Unsupported window {specification}: the window end must be after its start")
        return {"days": window_days, "start": opens, "end": closes}

    @classmethod
    def _plan_days(cls, days, specification) -> list[str]:
        if isinstance(days, str):
            days = [days]
        tokens: list[str] = []
        for item in days or ():
            tokens.extend(str(item).replace(",", " ").split())
        normalized: list[str] = []
        for item in tokens:
            token = str(item).strip().upper()
            if token in _PLAN_DAY_TOKENS:
                span = [token]
            elif "-" in token:
                first, _, last = token.partition("-")
                first, last = first.strip().upper(), last.strip().upper()
                if first not in _PLAN_DAY_TOKENS or last not in _PLAN_DAY_TOKENS \
                        or _PLAN_DAY_TOKENS.index(first) > _PLAN_DAY_TOKENS.index(last):
                    raise SmartMailError(f"Unsupported day range {token} in an allowed window")
                span = list(_PLAN_DAY_TOKENS[_PLAN_DAY_TOKENS.index(first):_PLAN_DAY_TOKENS.index(last) + 1])
            else:
                raise SmartMailError(f"Unsupported day {token} in an allowed window")
            for day in span:
                if day not in normalized:
                    normalized.append(day)
        if not normalized:
            raise SmartMailError(f"At least one day is required in the window {specification}")
        return normalized

    @staticmethod
    def _plan_time(value, specification) -> str:
        try:
            parsed = datetime.strptime(str(value).strip(), "%H:%M").time()
        except ValueError as error:
            raise SmartMailError(
                f"Unsupported window {specification}: times must use HH:MM") from error
        return f"{parsed.hour:02d}:{parsed.minute:02d}"

    @staticmethod
    def _plan_clock(value) -> time:
        hour, _, minute = str(value).partition(":")
        return time(int(hour), int(minute))

    def propose_plan(self, campaign_id: str) -> dict:
        """Propose sending times for a Campaign under its configured constraints.

        The proposal is deterministic: the same configuration, work and controlled
        time produce the same times.  Earlier proposals that were never confirmed
        are superseded so that only one proposed plan stays current.

        Actions are paced **per institution**.  A session is one allowed window on
        one local day; inside one session an institution contributes at most
        ``institution_limit`` advisor(s), while different institutions run in
        parallel.  Institutions never compare notes, so they may share a session;
        advisors inside one do, so that institution's advisors are spread over
        consecutive sessions.
        """
        self.get_campaign(campaign_id)
        configuration = self._plan_configuration(campaign_id)
        sessions = self._plan_sessions(configuration)
        slots = self._plan_slots(configuration)
        assigned: list[datetime] = []
        proposals = self._plan_entries(campaign_id)
        plannable = [proposal for proposal in proposals if proposal["status"] == "scheduled"]
        pacing = self._plan_pacing_constraint(plannable, sessions, configuration)
        self._plan_assign(sessions, plannable, configuration, assigned)
        for proposal in plannable:
            if proposal.get("slot") is None:
                proposal["status"] = "impossible"
                proposal["reason"] = "no_available_slot"
        not_placed = [proposal for proposal in plannable
                      if proposal["status"] == "impossible"]
        if not_placed:
            constraint = pacing or self._plan_binding_constraint(slots, configuration)
            if pacing:
                detail = (
                    f"The {configuration['horizon_days']}-day horizon offers "
                    f"{len(sessions)} session(s); at most "
                    f"{configuration['institution_limit']} advisor(s) of one institution may "
                    f"share a session, so this action was left unscheduled rather than placing "
                    f"two advisors of one institution in the same session")
            else:
                capacity = self._plan_capacity(slots, configuration)
                detail = (
                    f"The configured windows, spacing and limits provide {capacity} usable "
                    f"sending time(s) within the {configuration['horizon_days']}-day horizon "
                    f"for {len(plannable)} Ready action(s); this action was left unscheduled "
                    f"rather than violating the "
                    f"{_PLAN_CONSTRAINT_LABELS[constraint]} constraint")
            for proposal in not_placed:
                proposal["constraint"] = constraint
                proposal["detail"] = detail
        plan_id = str(uuid4())
        with self._db:
            self._db.execute(
                "UPDATE sending_plans SET status = 'superseded' "
                "WHERE campaign_id = ? AND status = 'proposed'", (campaign_id,))
            self._db.execute(
                "INSERT INTO sending_plans VALUES (?, ?, ?, 'proposed', ?, ?, ?, ?, ?, ?)",
                (plan_id, campaign_id, self._now(), configuration["timezone"],
                 json.dumps(configuration["windows"], ensure_ascii=False),
                 configuration["spacing_minutes"], configuration["daily_limit"],
                 configuration["horizon_days"], configuration["institution_limit"]))
            for sequence, proposal in enumerate(proposals, start=1):
                self._store_plan_proposal(plan_id, sequence, proposal, configuration)
        return self.get_plan(plan_id)

    def _plan_candidates(self, campaign_id: str) -> list[dict]:
        """Active Preparations in the Campaign's deterministic Task order."""
        return [self.get_preparation(row["id"])
                for row in self._db.execute(
                    "SELECT p.id FROM preparations p JOIN tasks t ON t.id = p.task_id "
                    "WHERE t.campaign_id = ? AND p.superseded_by IS NULL ORDER BY t.rowid",
                    (campaign_id,))]

    def _plan_entries(self, campaign_id: str) -> list[dict]:
        """One plan entry per active Preparation, before any sending time is assigned."""
        entries = []
        for preparation in self._plan_candidates(campaign_id):
            if self._db.execute("SELECT 1 FROM sent_records WHERE preparation_id = ?",
                                (preparation["id"],)).fetchone():
                entries.append({
                    "preparation": preparation, "slot": None, "status": "already_sent",
                    "reason": "already_sent", "constraint": "", "detail": (
                        "This Communication Action has already been executed; further "
                        "communication is a new linked action")})
                continue
            blocking = [finding["code"] for finding in preparation["readiness_findings"]
                        if finding["blocking"]]
            if blocking:
                entries.append({
                    "preparation": preparation, "slot": None, "status": "not_ready",
                    "reason": "not_ready", "constraint": "",
                    "detail": f"Preparation is not Ready; resolve: {', '.join(blocking)}"})
                continue
            entries.append({"preparation": preparation, "slot": None, "status": "scheduled",
                            "reason": "", "constraint": "", "detail": ""})
        return entries

    def _plan_slots_per_day(self, slots, configuration: dict) -> dict:
        """How many allowed instants each local day of the horizon offers."""
        zone = ZoneInfo(configuration["timezone"])
        per_day: dict = {}
        for slot in slots:
            day = slot.astimezone(zone).date()
            per_day[day] = per_day.get(day, 0) + 1
        return per_day

    def _plan_capacity(self, slots, configuration: dict) -> int:
        """How many actions the configured constraints can actually accommodate."""
        per_day = self._plan_slots_per_day(slots, configuration)
        return sum(min(count, configuration["daily_limit"]) for count in per_day.values())

    def _plan_binding_constraint(self, slots, configuration: dict) -> str:
        """The configured constraint that prevents the remaining actions from being placed."""
        per_day = self._plan_slots_per_day(slots, configuration)
        if not per_day:
            return "windows"
        if max(per_day.values()) > configuration["daily_limit"]:
            return "daily_limit"
        return "spacing_minutes"

    def _store_plan_proposal(self, plan_id: str, sequence: int, proposal: dict,
                             configuration: dict) -> None:
        preparation = proposal["preparation"]
        slot = proposal["slot"]
        self._db.execute(
            "INSERT INTO sending_plan_proposals "
            "(id, plan_id, preparation_id, task_id, sequence, status, reason, "
            "constraint_name, detail, scheduled_at, scheduled_utc, confirmation_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            (str(uuid4()), plan_id, preparation["id"], preparation["task_id"], sequence,
             proposal["status"], proposal["reason"], proposal["constraint"],
             proposal["detail"],
             slot.isoformat() if slot else "",
             slot.astimezone(timezone.utc).isoformat() if slot else ""))

    def _plan_sessions(self, configuration: dict) -> list[dict]:
        """Every allowed window occurrence in the horizon, each with its own instants.

        A session is one allowed window on one local day.  It is the unit that paces
        one institution against another: institutions run in parallel inside a
        session, one institution's advisors are spread across sessions.
        """
        zone = ZoneInfo(configuration["timezone"])
        now = self._instant().astimezone(zone)
        spacing = timedelta(minutes=configuration["spacing_minutes"])
        sessions: list[dict] = []
        seen: set[datetime] = set()
        for offset in range(configuration["horizon_days"]):
            date = now.date() + timedelta(days=offset)
            weekday = _PLAN_DAY_TOKENS[date.weekday()]
            for window in configuration["windows"]:
                if weekday not in window["days"]:
                    continue
                opens = datetime.combine(date, self._plan_clock(window["start"]), tzinfo=zone)
                closes = datetime.combine(date, self._plan_clock(window["end"]), tzinfo=zone)
                instants: list[datetime] = []
                slot = opens
                while slot <= closes:
                    instant = slot.astimezone(timezone.utc)
                    if slot > now and instant not in seen and self._plan_wall_time_exists(slot):
                        seen.add(instant)
                        instants.append(slot)
                    slot += spacing
                if instants:
                    sessions.append({"opens": opens, "closes": closes, "slots": instants})
        sessions.sort(key=lambda session: session["slots"][0])
        return sessions

    def _plan_slots(self, configuration: dict) -> list[datetime]:
        """Every allowed instant inside the configured windows, in chronological order."""
        return sorted(instant for session in self._plan_sessions(configuration)
                      for instant in session["slots"])

    def _plan_institution(self, task_id: str) -> str:
        """The institution an Outreach Task belongs to; pacing is per institution."""
        return self.get_task(task_id)["institution"]["name"] or task_id

    def _plan_pacing_constraint(self, plannable: list[dict], sessions: list[dict],
                                configuration: dict) -> str | None:
        """Whether one institution has more advisors than the horizon's sessions allow."""
        per_institution: dict[str, int] = {}
        for entry in plannable:
            key = self._plan_institution(entry["preparation"]["task_id"])
            per_institution[key] = per_institution.get(key, 0) + 1
        if not per_institution:
            return None
        if max(per_institution.values()) > len(sessions) * configuration["institution_limit"]:
            return "institution_pace"
        return None

    def _plan_assign(self, sessions: list[dict], plannable: list[dict],
                     configuration: dict, assigned: list[datetime]) -> None:
        """Place actions session by session, rotating through the institutions.

        Each instant of a session is offered to the next institution that still has
        an unplaced advisor and has not reached the session's per-institution limit.
        Spacing and the daily limit still hold across session and day boundaries.
        """
        zone = ZoneInfo(configuration["timezone"])
        spacing = timedelta(minutes=configuration["spacing_minutes"])
        limit = configuration["institution_limit"]
        groups: dict[str, list[dict]] = {}
        order: list[str] = []
        for entry in plannable:
            key = self._plan_institution(entry["preparation"]["task_id"])
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append(entry)
        counts: dict = {}
        previous: datetime | None = None
        for session in sessions:
            used: dict[str, int] = {}
            for instant in session["slots"]:
                if previous is not None and instant - previous < spacing:
                    continue
                day = instant.astimezone(zone).date()
                if counts.get(day, 0) >= configuration["daily_limit"]:
                    continue
                if all(not groups[key] or used.get(key, 0) >= limit for key in order):
                    break
                for key in order:
                    if not groups[key] or used.get(key, 0) >= limit:
                        continue
                    entry = groups[key].pop(0)
                    entry["slot"] = instant
                    assigned.append(instant)
                    counts[day] = counts.get(day, 0) + 1
                    used[key] = used.get(key, 0) + 1
                    previous = instant
                    break
            if not any(groups[key] for key in order):
                break

    @staticmethod
    def _plan_session_index(local: datetime, windows: list[dict]) -> int | None:
        """Which of the plan's windows a local time belongs to, if any.

        A session is one window on one day, so the window index together with the
        local date identifies the session an action is being placed in.
        """
        weekday = _PLAN_DAY_TOKENS[local.weekday()]
        stamp = local.strftime("%H:%M")
        for index, window in enumerate(windows):
            if weekday in window["days"] and window["start"] <= stamp <= window["end"]:
                return index
        return None

    @staticmethod
    def _plan_wall_time_exists(slot: datetime) -> bool:
        """Refuse a local wall time that the configured zone skips.

        A daylight-saving jump makes some clock readings nonexistent; silently
        shifting one would place an action at an instant the operator never chose.
        """
        resolved = slot.astimezone(timezone.utc).astimezone(slot.tzinfo)
        return (resolved.year, resolved.month, resolved.day, resolved.hour, resolved.minute) == \
            (slot.year, slot.month, slot.day, slot.hour, slot.minute)

    def get_plan(self, plan_id: str) -> dict:
        """The Sending Plan as batch review: exact content, times and exclusions."""
        row = self._db.execute("SELECT * FROM sending_plans WHERE id = ?", (plan_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Sending Plan not found: {plan_id}")
        configuration = {
            "timezone": row["timezone"], "windows": json.loads(row["windows"]),
            "spacing_minutes": row["spacing_minutes"], "daily_limit": row["daily_limit"],
            "horizon_days": row["horizon_days"],
            "institution_limit": row["institution_limit"]
            if "institution_limit" in row.keys() else PLAN_DEFAULTS["institution_limit"],
        }
        views = []
        for proposal in self._db.execute(
                "SELECT * FROM sending_plan_proposals WHERE plan_id = ? ORDER BY sequence",
                (plan_id,)):
            views.append(self._plan_proposal_view(proposal, row["timezone"]))
        return {
            "id": row["id"], "campaign_id": row["campaign_id"], "created_at": row["created_at"],
            "status": row["status"], "configuration": configuration,
            "proposals": [view for view in views if view["status"] == "scheduled"],
            "unavailable": [view for view in views
                            if view["status"] in ("not_ready", "already_sent")],
            "impossible": [view for view in views if view["status"] == "impossible"],
        }

    def _plan_proposal_view(self, proposal, timezone_name: str) -> dict:
        """One planned action with everything an operator reviews before Confirmation."""
        preparation = self.get_preparation(proposal["preparation_id"])
        task = self.get_task(proposal["task_id"])
        attachments = [
            {"id": slot["attachment"]["id"], "label": slot["label"],
             "name": slot["attachment"]["name"], "sha256": slot["attachment"]["sha256"],
             "size": slot["attachment"]["size"]}
            for slot in preparation["attachment_slots"] if slot["attachment"]]
        return {
            "preparation_id": proposal["preparation_id"], "task_id": proposal["task_id"],
            "status": proposal["status"], "reason": proposal["reason"],
            "constraint": proposal["constraint_name"], "detail": proposal["detail"],
            "scheduled_at": proposal["scheduled_at"], "timezone": timezone_name,
            "scheduled_utc": proposal["scheduled_utc"],
            "confirmation_id": proposal["confirmation_id"],
            "institution_name": task["institution"]["name"],
            "supervisor_name": task["supervisor"]["name"],
            "sender": preparation["sender"], "recipient": preparation["recipient"],
            "subject": preparation["subject"], "ready": preparation["ready"],
            "readiness_findings": preparation["readiness_findings"],
            "attachments": attachments,
            "message": self.preview_preparation(proposal["preparation_id"])["text"],
        }

    def list_plans(self, campaign_id: str) -> list[dict]:
        self.get_campaign(campaign_id)
        return [self.get_plan(row["id"]) for row in self._db.execute(
            "SELECT id FROM sending_plans WHERE campaign_id = ? ORDER BY rowid", (campaign_id,))]

    def adjust_plan(self, plan_id: str, preparation_id: str, scheduled_at) -> dict:
        """Set one planned action's exact time before Confirmation.

        The adjustment is validated against the plan's own configuration: an
        operator changes the configuration and re-proposes rather than smuggling
        a constraint violation into a confirmed Sending Plan.  Adjusting an
        already-confirmed action invalidates that Confirmation, because the
        authorization was bound to the previous exact time.
        """
        row = self._db.execute("SELECT * FROM sending_plans WHERE id = ?", (plan_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Sending Plan not found: {plan_id}")
        proposal = self._db.execute(
            "SELECT * FROM sending_plan_proposals WHERE plan_id = ? AND preparation_id = ?",
            (plan_id, preparation_id)).fetchone()
        if proposal is None:
            raise SmartMailError(
                f"Preparation is not part of this Sending Plan: {preparation_id}")
        if proposal["status"] in ("not_ready", "already_sent"):
            raise SmartMailError(
                f"This action cannot be scheduled for Confirmation: {proposal['detail']}")
        zone = ZoneInfo(row["timezone"])
        instant = self._plan_instant(scheduled_at, zone)
        self._validate_plan_instant(plan_id, proposal, instant, row)
        with self._db:
            if proposal["confirmation_id"]:
                self._db.execute(
                    "UPDATE confirmations SET status = 'invalidated', invalidated_reason = 'adjusted' "
                    "WHERE id = ? AND status = 'active'", (proposal["confirmation_id"],))
            self._db.execute(
                "UPDATE sending_plan_proposals SET status = 'scheduled', reason = '', "
                "constraint_name = '', detail = '', scheduled_at = ?, scheduled_utc = ?, "
                "confirmation_id = NULL WHERE id = ?",
                (instant.astimezone(zone).isoformat(),
                 instant.astimezone(timezone.utc).isoformat(), proposal["id"]))
            self._refresh_plan_status(plan_id)
        return self.get_plan(plan_id)

    def _plan_instant(self, value, zone: ZoneInfo) -> datetime:
        """An exact instant from an ISO-8601 local time or an explicit offset."""
        if isinstance(value, datetime):
            parsed = value
        else:
            text = str(value).strip().replace("Z", "+00:00")
            try:
                parsed = datetime.fromisoformat(text)
            except ValueError as error:
                raise SmartMailError(
                    f"Unsupported time {value!r}; use an exact ISO-8601 time such as "
                    "2026-09-15T09:00 or 2026-09-15T01:00:00Z") from error
        return parsed.replace(tzinfo=zone) if parsed.tzinfo is None else parsed

    def confirm_plan(self, plan_id: str, *, confirmed_at=None) -> dict:
        """Authorize every scheduled action of a Sending Plan in one operator action.

        Each action gets its own Confirmation, bound to its exact Preparation,
        content and execution time.  The whole batch is validated before anything
        is authorized, so a plan is never half-confirmed.
        """
        row = self._db.execute("SELECT * FROM sending_plans WHERE id = ?", (plan_id,)).fetchone()
        if row is None:
            raise SmartMailError(f"Sending Plan not found: {plan_id}")
        if row["status"] == "superseded":
            raise SmartMailError(
                "Sending Plan is superseded by a newer proposal; confirm the current plan")
        proposals = list(self._db.execute(
            "SELECT * FROM sending_plan_proposals WHERE plan_id = ? AND status = 'scheduled' "
            "ORDER BY sequence", (plan_id,)))
        if not proposals:
            raise SmartMailError("This Sending Plan has no scheduled action to confirm")
        now = self._instant()
        for proposal in proposals:
            preparation = self.get_preparation(proposal["preparation_id"])
            if preparation["status"] != "active":
                raise SmartMailError(
                    f"Preparation has been superseded; re-propose the Sending Plan: "
                    f"{proposal['preparation_id']}")
            blocking = [finding["code"] for finding in preparation["readiness_findings"]
                        if finding["blocking"]]
            if blocking:
                raise SmartMailError(
                    f"Preparation {proposal['preparation_id']} is not Ready; "
                    f"resolve: {', '.join(blocking)}")
            if self._db.execute("SELECT 1 FROM sent_records WHERE preparation_id = ?",
                                (proposal["preparation_id"],)).fetchone():
                raise SmartMailError(
                    "Preparation has already been sent; prepare a new linked Communication "
                    f"Action instead: {proposal['preparation_id']}")
            instant = self._plan_instant(proposal["scheduled_at"], ZoneInfo(row["timezone"]))
            if instant <= now:
                raise SmartMailError(
                    f"The sending time {proposal['scheduled_at']} has elapsed; confirm an "
                    "explicitly chosen replacement time (adjust the plan or re-propose it)")
        for proposal in proposals:
            confirmation = self.confirm(proposal["preparation_id"], execution={
                "kind": "scheduled", "scheduled_at": proposal["scheduled_at"],
                "timezone": row["timezone"]}, confirmed_at=confirmed_at)
            with self._db:
                self._db.execute(
                    "UPDATE sending_plan_proposals SET confirmation_id = ? WHERE id = ?",
                    (confirmation["id"], proposal["id"]))
        with self._db:
            self._refresh_plan_status(plan_id)
        return self.get_plan(plan_id)

    def _refresh_plan_status(self, plan_id: str) -> None:
        """A plan is confirmed only while every scheduled action carries a Confirmation."""
        rows = list(self._db.execute(
            "SELECT status, confirmation_id FROM sending_plan_proposals WHERE plan_id = ?",
            (plan_id,)))
        scheduled = [row for row in rows if row["status"] == "scheduled"]
        status = ("confirmed" if scheduled and all(row["confirmation_id"] for row in scheduled)
                  else "proposed")
        self._db.execute(
            "UPDATE sending_plans SET status = ? WHERE id = ? AND status != 'superseded'",
            (status, plan_id))

    def _validate_plan_instant(self, plan_id: str, proposal, instant: datetime, plan) -> None:
        """Refuse an exact time that the plan's configured constraints cannot allow."""
        zone = ZoneInfo(plan["timezone"])
        local = instant.astimezone(zone)
        if not self._plan_wall_time_exists(local):
            raise SmartMailError(
                f"The time {instant.isoformat()} does not exist in {plan['timezone']}")
        if instant <= self._instant():
            raise SmartMailError(
                f"The time {instant.isoformat()} must be in the future; an elapsed time needs "
                "an explicitly confirmed replacement time")
        weekday = _PLAN_DAY_TOKENS[local.weekday()]
        allowed = [window for window in json.loads(plan["windows"])
                   if weekday in window["days"]
                   and window["start"] <= local.strftime("%H:%M") <= window["end"]]
        if not allowed:
            raise SmartMailError(
                f"The time {local.isoformat()} is outside every allowed window of this Sending "
                f"Plan ({weekday} {local.strftime('%H:%M')} in {plan['timezone']})")
        windows = json.loads(plan["windows"])
        limit = plan["institution_limit"] if "institution_limit" in plan.keys() \
            else PLAN_DEFAULTS["institution_limit"]
        session = self._plan_session_index(local, windows)
        institution = self._plan_institution(proposal["task_id"])
        spacing = timedelta(minutes=plan["spacing_minutes"])
        others = list(self._db.execute(
            "SELECT preparation_id, task_id, scheduled_at FROM sending_plan_proposals "
            "WHERE plan_id = ? AND status = 'scheduled' AND id != ?",
            (plan_id, proposal["id"])))
        if session is not None:
            shared = sum(
                1 for other in others
                if self._plan_institution(other["task_id"]) == institution
                and self._plan_session_index(
                    self._plan_instant(other["scheduled_at"], zone).astimezone(zone), windows)
                == session)
            if shared + 1 > limit:
                raise SmartMailError(
                    f"At most {limit} advisor(s) of {institution} may share one session; "
                    f"{shared} already scheduled in it. Choose another session of this "
                    f"Sending Plan, or raise the institution limit in the rules")
        for other in others:
            if abs(instant - self._plan_instant(other["scheduled_at"], zone)) < spacing:
                raise SmartMailError(
                    f"The spacing of {plan['spacing_minutes']} minutes requires a later time: "
                    f"another action of this Sending Plan is already scheduled within it")
        day = local.date()
        same_day = sum(
            1 for other in others
            if self._plan_instant(other["scheduled_at"], zone).astimezone(zone).date() == day)
        if same_day + 1 > plan["daily_limit"]:
            raise SmartMailError(
                f"The daily limit of {plan['daily_limit']} action(s) is already reached on "
                f"{day.isoformat()}; this action needs another day")
