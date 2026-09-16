# Frontend foundation

The foundation extraction preserves the existing desktop Workspace and Intake
pages. Intake is still labeled **Source mapping** and remains a local sample.
The original page content, controls, dialogs, and Core operations are retained.

| Owner | Files | Responsibility |
| --- | --- | --- |
| App integration | `frontend/src/App.tsx` | Compose page lifetimes |
| Foundation | `frontend/src/app/` | Hash routes, navigation items, rail, topbar, shell CSS |
| Foundation | `frontend/src/shared/` | Design tokens, typed icons, SearchField, primitive CSS |
| Core integration | `frontend/src/core/` | Typed bridge commands and report models |
| Workspace | `frontend/src/pages/workspace/` | Workflow, task inspector, campaign state, mailbox and draft controls |
| Intake | `frontend/src/pages/intake/` | Source mapping, sample data, file staging, local inspection and filtering |

## Page development

Existing page work stays within its directory. Both pages consume the same shell
and may supply page-specific rail actions and topbar content. Those actions remain
owned by the page; the shell never imports pages, sample fixtures, or Core.
Use `navigate()` for route changes and `NavigationItem` for rail destinations.
New top-level pages need one coordinated route registration and App composition
change; ordinary page features need neither.

`AppShell` preserves the outer rail and page layout without adding wrappers around
page content or dialogs. `Topbar` provides the wordmark and breadcrumb. `SearchField`
preserves the controlled search interface. Shared CSS classes include primary and
secondary buttons, icon buttons, fields, headings, status colors and footer styles.
Tokens retain the original typography, palette, focus rings and shell colors.
Workspace CSS is scoped with `:where(.workspace-page)` to preserve selector
specificity. Intake keeps its existing `sm-` classes. Page styles must not supply
implicit dependencies to other pages. Existing breakpoint rules are retained;
desktop remains the supported target.

## Routes and state lifetime

- Empty hash, `#workflow`, or an unrecognized hash opens Workspace workflow.
- `#tasks` opens Workspace tasks, including on reload.
- `#source-mapping` retains the existing Intake deep link.
- Hash changes drive browser back/forward and active rail state.
- Workspace stays mounted while Intake is visible, preserving campaign, search,
  inspector and zoom state, as before. It renders no DOM during Intake.
- Intake mounts when entered and unmounts when left. Its sample edits, filters and
  staged file metadata reset on navigation or reload, as before.

## Core integration

Pages import `core` and report types from `src/core/`. The command/argument/result
contract matches the existing Python UI allowlist. Callers cannot choose an
arbitrary response type or mix a command with another command's arguments.
Transport remains same-origin JSON POST to `/api/core`; Vite still owns the private
stdio bridge. HTTP, transport and Core errors remain visible to the caller.
TypeScript models describe the bridge payload; they are not runtime validation of
untrusted data. Backend validation and the allowlist remain authoritative.

No new Core capability is introduced. Preparation readiness, duplicate checks,
confirmation invalidation, Rewrite eligibility, reconciliation and external action
authority remain in Core. Intake has no Core import and does not parse or persist
its staged files. See [workflow and bridge details](frontend-workflow.md).

## Verification

`npm test` checks route compatibility and Core transport success/failure behavior
using Node's built-in test runner (Node 24 or newer). `npm run build` checks all page
imports and TypeScript contracts. `npm run lint` checks the frontend source.
`python -m unittest tests.test_ui` exercises the actual persisted bridge contract.
Browser checks cover navigation history, page state lifetime, campaign dialogs,
Intake filtering/validation/inspection and the unchanged desktop layout.
