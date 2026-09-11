CREATE TABLE IF NOT EXISTS students (
    id TEXT PRIMARY KEY, name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mailboxes (
    id TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES students(id),
    address TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS institutions (
    id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS supervisors (
    id TEXT PRIMARY KEY, name TEXT NOT NULL,
    institution_id TEXT NOT NULL REFERENCES institutions(id), profile TEXT
);
CREATE TABLE IF NOT EXISTS supervisor_addresses (
    supervisor_id TEXT NOT NULL REFERENCES supervisors(id), address TEXT NOT NULL,
    UNIQUE(supervisor_id, address)
);
CREATE TABLE IF NOT EXISTS imports (
    id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(id),
    student_id TEXT NOT NULL REFERENCES students(id)
);
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY, import_id TEXT NOT NULL REFERENCES imports(id),
    name TEXT NOT NULL, content BLOB NOT NULL, sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY, student_id TEXT NOT NULL REFERENCES students(id),
    supervisor_id TEXT NOT NULL REFERENCES supervisors(id),
    campaign_id TEXT NOT NULL REFERENCES campaigns(id),
    UNIQUE(student_id, supervisor_id, campaign_id)
);
CREATE TABLE IF NOT EXISTS source_associations (
    task_id TEXT NOT NULL REFERENCES tasks(id), source_id TEXT NOT NULL REFERENCES sources(id),
    sheet TEXT NOT NULL, row INTEGER NOT NULL, evidence TEXT NOT NULL,
    UNIQUE(task_id, source_id, sheet, row)
);
CREATE TABLE IF NOT EXISTS exceptions (
    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id),
    source_id TEXT NOT NULL REFERENCES sources(id), code TEXT NOT NULL,
    detail TEXT NOT NULL, blocking INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS preparations (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    source_id TEXT NOT NULL REFERENCES sources(id),
    sender TEXT NOT NULL, recipient TEXT NOT NULL,
    subject TEXT NOT NULL DEFAULT '', body TEXT NOT NULL,
    internal_note TEXT NOT NULL DEFAULT '',
    association_evidence TEXT NOT NULL,
    superseded_by TEXT REFERENCES preparations(id),
    action_kind TEXT NOT NULL DEFAULT 'initial',
    linked_sent_record_id TEXT REFERENCES sent_records(id)
);
CREATE TABLE IF NOT EXISTS transformations (
    id TEXT PRIMARY KEY, preparation_id TEXT NOT NULL REFERENCES preparations(id),
    code TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS readiness_findings (
    id TEXT PRIMARY KEY, preparation_id TEXT NOT NULL REFERENCES preparations(id),
    code TEXT NOT NULL, detail TEXT NOT NULL, blocking INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS corrections (
    id TEXT PRIMARY KEY, preparation_id TEXT NOT NULL REFERENCES preparations(id),
    field TEXT NOT NULL, value TEXT NOT NULL, prior TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS attachment_slots (
    id TEXT PRIMARY KEY, preparation_id TEXT NOT NULL REFERENCES preparations(id),
    label TEXT NOT NULL, declared TEXT NOT NULL, basis TEXT NOT NULL,
    suggested_source_id TEXT REFERENCES sources(id),
    UNIQUE(preparation_id, label)
);
CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY, slot_id TEXT NOT NULL UNIQUE REFERENCES attachment_slots(id),
    name TEXT NOT NULL, content BLOB NOT NULL, sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS document_findings (
    id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id),
    code TEXT NOT NULL, detail TEXT NOT NULL, blocking INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS confirmations (
    id TEXT PRIMARY KEY,
    preparation_id TEXT NOT NULL REFERENCES preparations(id),
    task_id TEXT NOT NULL REFERENCES tasks(id),
    execution_kind TEXT NOT NULL,
    execution_detail TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    attachments_digest TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    invalidated_reason TEXT NOT NULL DEFAULT '',
    confirmed_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS execution_attempts (
    id TEXT PRIMARY KEY,
    confirmation_id TEXT NOT NULL REFERENCES confirmations(id),
    preparation_id TEXT NOT NULL REFERENCES preparations(id),
    task_id TEXT NOT NULL REFERENCES tasks(id),
    sequence INTEGER NOT NULL,
    state TEXT NOT NULL,
    request TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '',
    phase TEXT NOT NULL DEFAULT 'intent_recorded',
    intent_at TEXT NOT NULL DEFAULT '',
    submission_started_at TEXT NOT NULL DEFAULT '',
    outcome_observed_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS sent_records (
    id TEXT PRIMARY KEY,
    preparation_id TEXT NOT NULL REFERENCES preparations(id),
    task_id TEXT NOT NULL REFERENCES tasks(id),
    attempt_id TEXT NOT NULL REFERENCES execution_attempts(id),
    content TEXT NOT NULL,
    evidence TEXT NOT NULL,
    reference TEXT NOT NULL DEFAULT '',
    action_kind TEXT NOT NULL DEFAULT 'initial',
    follows_sent_record_id TEXT REFERENCES sent_records(id)
);
CREATE TABLE IF NOT EXISTS sent_attachments (
    id TEXT PRIMARY KEY,
    sent_record_id TEXT NOT NULL REFERENCES sent_records(id),
    label TEXT NOT NULL, name TEXT NOT NULL,
    content BLOB NOT NULL, sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS execution_flow (
    campaign_id TEXT PRIMARY KEY REFERENCES campaigns(id),
    state TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS mailbox_observation_runs (
    id TEXT PRIMARY KEY,
    mailbox_id TEXT NOT NULL REFERENCES mailboxes(id),
    adapter TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '',
    evidence_coverage TEXT NOT NULL,
    capabilities TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mailbox_message_observations (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES mailbox_observation_runs(id),
    direction TEXT NOT NULL,
    folder TEXT NOT NULL,
    platform_reference TEXT NOT NULL DEFAULT '',
    counterpart TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    observed_time TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    ambiguity TEXT NOT NULL DEFAULT '',
    evidence TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reconciliations (
    id TEXT PRIMARY KEY,
    mailbox_id TEXT NOT NULL REFERENCES mailboxes(id),
    observation_run_id TEXT NOT NULL REFERENCES mailbox_observation_runs(id),
    observed_at TEXT NOT NULL,
    summary TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS duplicate_checks (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    preparation_id TEXT NOT NULL REFERENCES preparations(id),
    checked_at TEXT NOT NULL,
    finding TEXT NOT NULL,
    review_required INTEGER NOT NULL DEFAULT 0,
    basis TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    evidence_coverage TEXT NOT NULL,
    matches TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reconciliation_findings (
    id TEXT PRIMARY KEY,
    reconciliation_id TEXT NOT NULL REFERENCES reconciliations(id),
    message_observation_id TEXT REFERENCES mailbox_message_observations(id),
    finding TEXT NOT NULL,
    local_kind TEXT NOT NULL DEFAULT '',
    local_id TEXT NOT NULL DEFAULT '',
    basis TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);
