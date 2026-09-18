## Agent skills

### Language consistency

English is the single presentation language. User-visible strings (UI, extension
popup/manifest, status and error messages) must be English; Chinese inside
recognition/intake matching rules and DOM-matching literals is core logic and
must not be touched. See `.trae/rules/language-consistency.md`. Multilingual
(i18n) support is planned for a later round — see
`.scratch/language-consistency/issues/01-multilingual-support.md`.

### Global frontend layout

Every main page must fit the available viewport responsively, with no page-level
scrolling in either direction. Adapt density, spacing, and internal regions to
window width and height. Overflow belongs inside bounded content regions, and
all controls and content must remain reachable. Follow `frontend/AGENTS.md` and
`docs/frontend-foundation.md` for the shared viewport contract.

### Issue tracker

Issues are tracked as local Markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Domain docs

This is a single-context repository. See `docs/agents/domain.md`.
