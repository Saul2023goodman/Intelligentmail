# 04: Close the preparation-material loop in the workspace

Status: ready-for-agent
Blocked by: None (can start immediately)

**What to build:** Everything the operator must do to a Preparation before it is Ready happens in the workspace: replace its content with a fresh Preparation from a revised imported document — a Rewrite — inspect the Superseded Preparation as history, add, replace or remove attachment slots, and open the preserved Source Material a Preparation came from. Today the workspace documents source-based Rewrite while no page offers it, so a blocking replacement finding can be seen and not resolved; attachment slots can only be confirmed, never added or removed; and preserved sources can only be listed.

## Acceptance criteria

- [ ] A blocking replacement finding is resolvable in the workspace by choosing an imported document belonging to the same Student and Campaign, producing a fresh Preparation of the same Outreach Task.
- [ ] The prior Preparation becomes Superseded, its applicable Confirmation does not transfer, and an unresolved Execution Attempt must be stopped first, exactly as the existing rules require.
- [ ] The operator can inspect the Outreach Task's Preparation history, including each version's content, Source Association and Transformation Records, newest first.
- [ ] The operator can add an attachment slot, replace its bytes from a preserved Source Material or a local file, and remove a slot; confirmed bytes stay immutable snapshots and readiness is recomputed afterwards.
- [ ] The operator can open, or save a copy of, a preserved Source Material; editing the copy never changes preserved bytes.
- [ ] A source-based Rewrite refuses documents outside the Student and Campaign scope, and no action on this path writes to a mailbox.

## Comments

2026-09-17: Raised from the frontend ↔ Core adaptation review. The workspace README and the workflow mapping both state that the editor performs a source-based Rewrite, and the bridge exposes the command with its candidate sources, but no page invokes it; the attachment-slot add and remove commands and the materialised-source command exist only in the terminal shell.