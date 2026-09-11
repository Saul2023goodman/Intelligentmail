# 15: Associate replies and recognize automatic replies

Status: ready-for-agent
Labels: ready-for-agent
Blocked by: 03, 06

**What to build:** Inspect received messages, resolve ambiguous associations, and expose reliable reply state for follow-up eligibility.

## Acceptance criteria

- [ ] Define supported deterministic association evidence during coding; only reliable matches become Associated Replies.
- [ ] Surface ambiguous task associations for operator review within SmartMail.
- [ ] Associated Ordinary Replies stop no-reply eligibility without classifying interest, rejection, or document requests.
- [ ] Recognized Automatic Replies use supported explicit rules, remain separately inspectable, and do not themselves stop no-reply eligibility.
- [ ] Do not treat uncertain automatic-reply detection as inferred semantic understanding; document and test its supported boundary.
- [ ] Persist associations and observations across restart; boundary tests cover reliable links, ambiguous links, supported automatic replies, and ordinary messages.

## Testing boundary

Exercise operator-visible behavior through the core command/query boundary used by the terminal shell, with persistent local state and a controlled mailbox adapter where needed. Verify enabled real browser capabilities separately; do not test internal implementation structure.

## Scope and references

Parent: SmartMail Phase One: Supervisor Outreach Operations specification. Use the canonical domain glossary. No AI, no phase-one frontend, and no routine exported-workbook workflow. Each slice includes its terminal interaction, core behavior, persistence, and behavioral tests.

