# Supported Execution Recovery Pattern 08

Ticket 08 extends the persisted Execution Ledger with crash-boundary evidence and an explicit operator recovery path. It is implemented at the same core command/query boundary used by the terminal shell; it does not claim that simulated outcomes verify a live mailbox platform.

## Persisted attempt phases

An Execution Attempt records a committed intent before external submission, then a separate submission-start marker, then adapter outcome evidence. The observable states are:

- `not_attempted`: intent exists, but the adapter boundary was not crossed; this same attempt may be reused by `execution resume`.
- `in_progress`: submission started and the local process has not established an outcome.
- `unknown`: the external result is unresolved; it is never treated as failure and is never retried blindly.
- `sent`, `failed`, and `stopped`: terminal local ledger states, with evidence retained.

If restart finds `in_progress`, it converts the attempt to `unknown`, persists a `recovery_required` pause, and leaves local Preparation, inspection, and reporting available. If adapter-confirmed `sent` was persisted before Sent Record creation completed, restart finishes the local Sent Record without another external request.

## Reconciliation and Manual Takeover

```powershell
python -m smartmail execution takeover ATTEMPT_ID --detail 'operator completed the mailbox step'
python -m smartmail execution reconcile-and-continue ATTEMPT_ID [CONFIRMATION_ID ...]
python -m smartmail execution resume --campaign CAMPAIGN_ID
```

`takeover` records Manual Takeover but does not establish Sent. `reconcile-and-continue` performs a read-only mailbox observation, resolves the attempt only when one unambiguous outbound observation is mailbox-confirmed `sent`, and may then run explicitly supplied still-valid Confirmations. A draft, partial observation, authentication interruption, operator acknowledgment, or ambiguous match leaves the attempt `unknown`.

## Confirmation validity

Confirmations retain their operator confirmation time and optional ISO-8601 validity fields such as `expires_at` or `confirmed_time`. Expired work pauses with `confirmation_expired`; a fresh explicit Confirmation is required before execution. Existing failure, duplicate, authentication, and recovery pauses are not bypassed by restart resume.

The controlled adapter supports `sent`, `failed`, `unknown`, `authentication_required`, and crash fixtures (`before_submission`, `during_submission`, and `after_success`) for repeatable boundary tests. These fixtures are evidence simulations only.
