# Frontend ownership

Read `README.md` and `../docs/frontend-foundation.md` before changing the frontend.

- Workspace work belongs in `src/pages/workspace/`.
- Intake (the Source mapping prototype) work belongs in `src/pages/intake/`.
- Keep page state, fixtures, dialogs, domain presentation, and styles in that page's directory. Do not import one page's implementation from another page.
- Reuse `src/app/` for shell/navigation/routing and `src/shared/` for tokens, icons, search, and primitive styles. Existing page work should not require editing `App.tsx`, `main.tsx`, global styles, or the other page.
- Scope new page CSS under its page root or use CSS modules. Do not add global element selectors in page CSS.
- Call Core through `src/core/`. Keep the command contract aligned with `smartmail/ui.py`; do not implement domain decisions or direct mailbox access in pages.
- Shared interface changes require coordination across page worktrees. Register new top-level routes in `src/app/routes.ts` and compose them in `src/App.tsx` as an integration change.
- Preserve the desktop layouts and existing behavior unless the task explicitly requests a change.
- Every main page must fit the available viewport in both dimensions with no page-level scrolling. Use the shared shell's bounded `main` region, adapt density and spacing to window width and height, and place overflow only in named internal regions. Never rely on clipping to hide inaccessible controls or content. Test resizing, short windows, narrow windows, long content, and dialogs. See the viewport contract in `../docs/frontend-foundation.md`.

Checks: `npm run build`, `npm run lint`, `npm test`; for Core changes also run `python -m unittest tests.test_ui` from the repository root. Check affected page flows in a desktop browser.
