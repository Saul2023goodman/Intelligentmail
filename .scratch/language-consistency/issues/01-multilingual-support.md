# 01: Multilingual (i18n) support

Status: open
Labels: future, i18n
Blocked by: —

**What to build:** Introduce a proper localization layer so the UI and extension
can present English plus additional languages, replacing the current inline
English-only strings.

## Notes

- This round (2026-09-18) only unified all user-visible strings to English and
  established the language boundary in `.trae/rules/language-consistency.md`.
  No translation framework was introduced; strings remain inline.
- When i18n lands, extract UI strings into message catalogs (e.g. `frontend/src/i18n/`
  and extension `_locales/`), keeping the functional Chinese matchers in
  `smartmail/` and the 163 DOM literals untouched — they are data, not presentation.

## Acceptance criteria

- [ ] Language switcher with English as default; persisted per user.
- [ ] All UI strings sourced from catalogs, not inline literals.
- [ ] Extension uses `_locales/` message keys for popup and manifest strings.
- [ ] Encoding contract preserved: all catalogs UTF-8.
