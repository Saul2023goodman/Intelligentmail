---
alwaysApply: true
---

# Language consistency

English is the single presentation language of this product.

## Scope — what must be English

- All user-visible strings: React UI (`frontend/src/`), extension popup and
  manifest (`extensions/netease163/`), status messages, error messages, labels,
  placeholders, and `aria-*` text.
- New code comments and new documentation written for operators or developers.

## Boundaries — do NOT touch (core logic)

- Chinese inside recognition and intake matching rules is functional data, not
  presentation. Never translate or remove it:
  - `smartmail/recognition.py`, `smartmail/intake.py`,
    `smartmail/_operations/replies.py`, `smartmail/_operations/preparations.py`
    (regexes, keyword sets, column-label vocabularies).
  - DOM-matching literals in `extensions/netease163/reader.js`, `observe.js`,
    `compose.js` (folder labels, button texts such as "写 信"/"发送"/"纯文本"
    that are compared against the live 163.com page).
- Test fixtures that model Chinese source material (e.g. `tests/test_recognition.py`,
  `frontend/tests/recognition-model.test.mjs`, `extensions/netease163/tests/browser-smoke.cjs`)
  keep their Chinese sample data; it is the input the matchers must handle.
- Historical documents under `docs/` and `.scratch/` are frozen records; do not
  translate them.

## Encoding

- All text files are UTF-8 (verified by repository scan). Read and write text
  files with an explicit `encoding="utf-8"` in Python and keep `<meta charset>`
  declarations intact in HTML.

## Future work (not this round)

- Multi-language support (i18n) is planned later. Until then keep English strings
  inline; do not introduce a translation framework. See
  `.scratch/language-consistency/issues/01-multilingual-support.md`.
