# 01: Confirmed Follow-up trigger and Ready Pool handoff

Status: resolved

- Add versioned, enabled Follow-up timing configuration and an idempotent Core processor.
- Create one linked Ready Preparation per substantive trigger and stop at Ready Pool.
- Expose allowlisted workspace/configure/process commands.
- Merge current Mailbox monitoring and Follow-up trigger configuration into one responsive workspace.
- Move historical mailbox evidence to Records and keep Batch execution as the only operational queue.
- Drive processing while the app is active and verify Core/UI contracts.

## Comments

2026-09-18: The operator clarified that saving Follow-up timing configuration is itself Confirmation; no per-message human Confirmation is required.

2026-09-18: Superseded the original interpretation. Configuration confirms only
the creation trigger. A triggered action enters the global Ready Pool exactly once;
Batch execution creates the exact sending Confirmation and performs execution.

## Answer

`process_follow_up_automation` now ends after creating a linked Ready Preparation.
The merged Mailbox monitor exposes current mailbox evidence, the confirmed trigger
policy and the Ready Pool handoff; historical evidence lives in Records. The global
navigation follows that direction by placing Mailbox before Batch execution.
