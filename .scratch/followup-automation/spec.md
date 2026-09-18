# Follow-up automation

An operator configures and enables one Campaign Follow-up Rule. Saving its trigger, content templates, and timing confirms the trigger policy, not a send. SmartMail evaluates deterministic eligibility and creates one linked Follow-up Action with a Ready Preparation. It stops at the global Ready Pool; Batch execution owns selection, planning, exact sending Confirmation and execution.

The trigger processor must remain idempotent and must stop for a reliably associated Ordinary Reply or ambiguous reply review. Recognized Automatic Replies do not stop eligibility. Readiness, duplicate, mailbox capability and paused-flow safeguards remain in Batch execution. Every triggered Preparation is visible in the existing execution queue and later ledger.

The frontend merges Follow-up configuration and trigger status into the viewport-bounded Mailbox monitoring page. Mailbox owns current observation and refresh; Records owns historical Observation and Reconciliation evidence; Batch execution remains the sole operational queue. A small app-level driver asks Core to process the selected Campaign while the local app is running; Core may create a Ready Preparation but performs no external effect.
