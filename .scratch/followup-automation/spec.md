# Follow-up automation

An operator configures and enables one Campaign Follow-up Rule. Saving its trigger, content templates, and timing is the Follow-up Automation Confirmation. From then on SmartMail evaluates deterministic eligibility, creates linked Follow-up Actions, derives exact per-action Confirmations, and enters the existing Execution Flow without per-message operator work.

The automation must remain idempotent and must stop for a reliably associated Ordinary Reply, ambiguous reply review, duplicate suspicion, a non-Ready Preparation, an unavailable mailbox capability, or a paused Execution Flow. Recognized Automatic Replies do not stop eligibility. Every concrete action remains visible in the existing execution queue and ledger.

The frontend merges Follow-up configuration and trigger status into the viewport-bounded Mailbox monitoring page. Mailbox owns current observation and refresh; Records owns historical Observation and Reconciliation evidence; Execution remains the sole operational queue. A small app-level driver asks Core to process the selected Campaign while the local app is running; Core owns all decisions and external effects.
