"""SmartMail composition and store lifecycle."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .mailbox import DisabledMailbox

from ._operations.records import RecordsOperations
from ._operations.reconciliation import ReconciliationOperations
from ._operations.duplicates import DuplicateOperations
from ._operations.replies import ReplyOperations
from ._operations.followups import FollowUpOperations
from ._operations.reporting import ReportingOperations
from ._operations.attachments import AttachmentOperations
from ._operations.preparations import PreparationOperations
from ._operations.confirmations import ConfirmationOperations
from ._operations.execution import ExecutionOperations
from ._operations.recovery import RecoveryOperations
from ._operations.planning import PlanningOperations
from ._operations.schedules import SchedulesOperations
from ._operations.runs import RunOperations


class SmartMail(
    RecordsOperations,
    ReconciliationOperations,
    DuplicateOperations,
    ReplyOperations,
    FollowUpOperations,
    ReportingOperations,
    AttachmentOperations,
    PreparationOperations,
    ConfirmationOperations,
    ExecutionOperations,
    RecoveryOperations,
    PlanningOperations,
    SchedulesOperations,
    RunOperations,
):
    """Persistent command/query interface for local outreach operations.

    Private operation groups share this instance and its SQLite transaction scope.
    Only this class owns lifecycle, dependencies and database initialization.
    """

    def __init__(self, home: Path, mailbox=None, clock=None):
        self.home = Path(home).resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.mailbox = mailbox if mailbox is not None else DisabledMailbox()
        #: The controlled time this store reasons with. Replacing it makes every
        #: date-dependent decision (planning windows, expiry) reproducible.
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self.store_path = self.home / "smartmail.sqlite3"
        self._db = sqlite3.connect(self.store_path, timeout=10)
        self._db.row_factory = sqlite3.Row
        # The store is the durable system of record, not a process-local cache.
        # WAL keeps committed records recoverable across normal application
        # shutdowns while allowing the extension bridge to read concurrently.
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.execute("PRAGMA synchronous = FULL")
        self._db.execute("PRAGMA busy_timeout = 10000")
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS campaigns ("
            "id TEXT PRIMARY KEY, name TEXT NOT NULL, student_id TEXT REFERENCES students(id))"
        )
        self._db.commit()
        self._db.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        self._migrate()

    def _migrate(self) -> None:
        """Keep an existing local store usable as the versioned Preparation schema grows."""
        campaign_columns = {row["name"] for row in self._db.execute("PRAGMA table_info(campaigns)")}
        if "student_id" not in campaign_columns:
            self._db.execute(
                "ALTER TABLE campaigns ADD COLUMN student_id TEXT REFERENCES students(id)")
            self._link_students_to_campaigns()
            self._db.commit()
        columns = {row["name"] for row in self._db.execute("PRAGMA table_info(preparations)")}
        if "superseded_by" not in columns:
            self._db.execute(
                "ALTER TABLE preparations ADD COLUMN superseded_by TEXT REFERENCES preparations(id)")
            self._db.commit()
        for table, column, definition in (
            ("preparations", "action_kind", "action_kind TEXT NOT NULL DEFAULT 'initial'"),
            ("preparations", "linked_sent_record_id",
             "linked_sent_record_id TEXT REFERENCES sent_records(id)"),
            ("sent_records", "action_kind", "action_kind TEXT NOT NULL DEFAULT 'initial'"),
            ("sent_records", "follows_sent_record_id",
             "follows_sent_record_id TEXT REFERENCES sent_records(id)"),
            ("execution_attempts", "phase",
             "phase TEXT NOT NULL DEFAULT 'legacy'"),
            ("execution_attempts", "intent_at",
             "intent_at TEXT NOT NULL DEFAULT ''"),
            ("execution_attempts", "submission_started_at",
             "submission_started_at TEXT NOT NULL DEFAULT ''"),
            ("execution_attempts", "outcome_observed_at",
             "outcome_observed_at TEXT NOT NULL DEFAULT ''"),
            ("execution_attempts", "updated_at",
             "updated_at TEXT NOT NULL DEFAULT ''"),
            ("confirmations", "confirmed_at",
             "confirmed_at TEXT NOT NULL DEFAULT ''"),
            ("plan_configurations", "institution_limit",
             "institution_limit INTEGER NOT NULL DEFAULT 1"),
            ("sending_plans", "institution_limit",
             "institution_limit INTEGER NOT NULL DEFAULT 1"),
            ("follow_up_rules", "enabled",
             "enabled INTEGER NOT NULL DEFAULT 0"),
            ("follow_up_rules", "timezone",
             "timezone TEXT NOT NULL DEFAULT 'UTC'"),
            ("follow_up_rules", "send_time",
             "send_time TEXT NOT NULL DEFAULT ''"),
            ("follow_up_rules", "revision",
             "revision INTEGER NOT NULL DEFAULT 0"),
            ("follow_up_rules", "policy_digest",
             "policy_digest TEXT NOT NULL DEFAULT ''"),
            ("follow_up_rules", "confirmed_at",
             "confirmed_at TEXT NOT NULL DEFAULT ''"),
            ("follow_up_rules", "updated_at",
             "updated_at TEXT NOT NULL DEFAULT ''"),
            ("follow_up_actions", "rule_revision",
             "rule_revision INTEGER NOT NULL DEFAULT 0"),
            ("follow_up_actions", "policy_digest",
             "policy_digest TEXT NOT NULL DEFAULT ''"),
        ):
            existing = {row["name"] for row in self._db.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                self._db.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
                self._db.commit()
        self._recover_unfinished_execution()

    def _link_students_to_campaigns(self) -> None:
        """Recover the Student-to-Campaign link a store recorded only by name.

        Earlier sessions established one Campaign per Student but persisted no
        relationship, so the link is recovered once, and only where the intent is
        unambiguous: exactly one unlinked Campaign and exactly one Student share the
        name. Name matching is never used again after this migration.
        """
        unlinked: dict[str, list[str]] = {}
        for row in self._db.execute("SELECT id, name FROM campaigns"):
            unlinked.setdefault(row["name"], []).append(row["id"])
        owners: dict[str, list[str]] = {}
        for row in self._db.execute("SELECT id, name FROM students"):
            owners.setdefault(row["name"], []).append(row["id"])
        for name, campaign_ids in unlinked.items():
            student_ids = owners.get(name, [])
            if len(campaign_ids) == 1 and len(student_ids) == 1:
                self._db.execute("UPDATE campaigns SET student_id = ? WHERE id = ?",
                                 (student_ids[0], campaign_ids[0]))

    def _instant(self) -> datetime:
        """The store's controlled instant, always timezone-aware."""
        now = self._clock()
        return now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now

    def _now(self) -> str:
        return self._instant().isoformat()

    @staticmethod
    def _parse_timestamp(value):
        if isinstance(value, datetime):
            parsed = value
        elif value:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return None
        else:
            return None
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._db.close()
