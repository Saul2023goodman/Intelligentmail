# Treat enabled Follow-up configuration as standing Confirmation

Status: superseded by ADR-0003

An operator saving an enabled Follow-up Rule, its content templates, and its timing configuration creates a versioned Follow-up Automation Confirmation. When that version triggers, SmartMail may prepare the linked Follow-up Action, derive an exact per-action Confirmation, and enter execution without another human step; execution still rechecks content and attachment digests, reliably associated Ordinary Replies, duplicate evidence, readiness, mailbox capability, and Execution Flow state. We chose this two-level authorization instead of either repeated per-message approval or a direct rule-to-mailbox shortcut so unattended follow-up remains auditable through the existing Confirmation and Execution Ledger.
