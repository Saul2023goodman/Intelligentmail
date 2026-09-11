# Supported Duplicate Detection Pattern 07

Established as deterministic detection against recorded sends and persisted mailbox observations. Ticket 07 prevents Repeat Execution of an already executed Communication Action and flags repeated initial outreach for the same Student and Supervisor within a Campaign before anything is submitted to the mailbox.

## Operator commands

```powershell
python -m smartmail duplicate check PREPARATION_ID
python -m smartmail duplicate list --campaign CAMPAIGN_ID
python -m smartmail duplicate show CHECK_ID
python -m smartmail preparation link-follow-up PREPARATION_ID [--sent SENT_RECORD_ID]
```

Each `duplicate check` persists an immutable record with its finding, matches and Evidence Coverage, so the operator can inspect the evidence behind a refusal after restarting.

## Evidence Coverage

A check inspects two sources and records both:

| Source | Scope | Completeness |
| --- | --- | --- |
| `sent_records` | The Campaign's immutable Sent Records | Always complete for the Campaign |
| `mailbox_observations` | Outbound observations in the Student's own Mailbox | `supported_scope_complete` or `complete` on every observation run for that Mailbox |

The coverage record also carries the Student, Supervisor, Campaign and every known Supervisor address, plus explicit limitations. **Incomplete coverage alone never blocks execution.** With no match, the check reports No Duplicate Found qualified by that coverage, and the recorded limitation states that no match is not proof that no prior send exists outside the inspected scope.

## Deterministic matching rules

The Mailbox account identifies the Student and the recipient identifies the Supervisor.

1. **Repeat Execution** — a Sent Record already exists for this exact Preparation. Basis `same_action`. Requires review; execution of a confirmed action is already refused by the authorization guard.
2. **Duplicate Suspicion** — an observed outbound `sent` message whose recipient is a known address of this Task's Supervisor, including known alternate addresses. Basis `known_supervisor_address`.
3. **Ambiguous Match** — evidence that points at this Supervisor but cannot be established:
   - `conflicting_identity`: the Task's Supervisor identity is still unresolved (`identity_ambiguity`). Resolved by `task confirm-identity`, after which the same observation yields a deterministic finding.
   - `incomplete_evidence`: the observation itself is flagged ambiguous by the refresh. Resolved by a cleaner observation; a deterministically matched observation takes precedence over an ambiguous one.
4. **No Duplicate Found** — no source matched within the recorded coverage.

Different Students stay distinct: observations belong to one Mailbox, so another Student's prior send to the same Supervisor is never a duplicate for this Task. A prior send to an unrelated recipient is likewise not a match.

Linked Follow-up Actions are excluded from initial-outreach duplication. A Preparation carries `action_kind` (default `initial`) and an optional link to earlier outreach; `preparation link-follow-up` marks it, and the kind is frozen into its Sent Record. A linked Follow-up Action reports `linked_follow_up` instead of a duplicate suspicion, and Repeat Execution still applies to it.

## Reconciliation before execution

`execution run` re-checks duplicates for each Confirmation after authorization and before creating an Execution Attempt:

- a `duplicate_suspicion` or `ambiguous_match` finding **pauses the current Execution Flow** with the finding as its reason and submits nothing;
- a batch stops at the affected action, keeping already executed attempts;
- `execution status --campaign` reports the pause, and a later `execution run` refuses while the flow is paused;
- No Duplicate Found proceeds, including when coverage is incomplete.

Existing behaviour is unchanged: Repeat Execution, changed content and new readiness blockers are still refused by the authorization guard rather than paused.

## Controlled fixtures

Ordinary tests pass `observations` through the controlled adapter and exercise the same core command/query boundary as the terminal shell. These fixtures establish repeatable SmartMail behaviour; live 163.com verification is a separate activity and no new mailbox capability is claimed by this ticket.
