# Frontend foundation

The foundation preserves the existing desktop Workspace and Intake layouts.
Intake remains labeled **Source mapping** and is backed by the local Core bridge.
The original page content, controls, dialogs, and Core operations are retained.

| Owner | Files | Responsibility |
| --- | --- | --- |
| App integration | `frontend/src/App.tsx` | Compose page lifetimes |
| Foundation | `frontend/src/app/` | Hash routes, navigation items, rail, topbar, shell CSS |
| Foundation | `frontend/src/shared/` | Design tokens, typed icons, SearchField, primitive CSS |
| Core integration | `frontend/src/core/` | Typed bridge commands and report models |
| Workspace | `frontend/src/pages/workspace/` | Workflow graph, the single global Student (Campaign) switcher and student creation |
| Intake | `frontend/src/pages/intake/` | Source mapping, browser source import, Core evidence inspection and filtering |
| Review | `frontend/src/pages/review/` | Preparation readiness, evidence inspection and supported operator corrections |

## Page development

Existing page work stays within its directory. Every page consumes the same shell,
which owns the complete navigation rail and active-route treatment. Pages may add
topbar content, but never page-specific rail destinations or rail sizing. The shell
never imports pages, sample fixtures, or Core.
Use `navigate()` for route changes and `NavigationItem` for rail destinations.
New top-level pages need one coordinated route registration and App composition
change; ordinary page features need neither.

### Shared page header

Every page that opens with a title band composes `PageHeader` from
`src/app/page-header.tsx`, passing `eyebrow`, `title`, an optional `badge` or
`subtitle`, read-only live `meta`, and its own `actions`. `src/app/page-header.css`
owns that band's typography, spacing, wrapping and responsive hiding; pages own only
the widgets they hand in.

The band is a single row on wide windows: eyebrow and title share one baseline, meta
and actions sit on the right. It reduces to the title plus actions on narrow or short
windows rather than truncating the title — when the row cannot fit, meta and actions
wrap below instead. Pages must not reintroduce a bespoke heading block, a stacked
eyebrow/headline/deck combination, a second heading row, or their own page-title
sizing. Workflow and Source mapping have no title band; they begin with their own
first-level section headings and consume the same density variables so their rhythm
still matches the other routes.

`AppShell` preserves the outer rail and page layout without adding wrappers around
page content or dialogs. `Topbar` provides the wordmark and breadcrumb. `SearchField`
preserves the controlled search interface. Shared CSS classes include primary and
secondary buttons, icon buttons, fields, headings, status colors and footer styles.
Tokens retain the original typography, palette, focus rings and shell colors.
Workspace CSS is scoped with `:where(.workspace-page)` to preserve selector
specificity. Intake keeps its existing `sm-` classes. Page styles must not supply
implicit dependencies to other pages.

## Global workspace scope

Workflow is the only place where the operator selects or creates a Student. Because
each Student owns exactly one Campaign, that selection establishes the global
Student, Campaign and mailbox scope for every route. The scope is persisted locally
and stays live while pages mount and unmount. Other pages show the shared scope as a
read-only topbar summary linking back to Workflow; they must not add Campaign or
Student selectors of their own.

## Global viewport contract

Every main page fits the available viewport responsively, with no page-level
horizontal or vertical scrolling. This supersedes the previous desktop-only,
non-responsive layout guidance.

- `html`, `body`, and `#root` are bounded. `AppShell` occupies `100dvh` and its
  `.workspace` is a constrained flex column. Page-level overflow is prohibited.
- Page chrome and footer keep their own space; the direct `main` child fills the
  remainder with `min-height: 0`. Nested flex/grid regions must also have zero
  minimum dimensions. Avoid fixed content minimum heights that enlarge the page.
- `src/app/viewport.css` owns shared responsive density variables (page inset,
  heading spacing, bar heights and region spacing), loaded after page styles.
  Pages consume these variables and own their internal width/height breakpoints.
- Those variables are the shared chrome budget: `--bar-height` for the topbar,
  `--heading-block` for the page header band, `--toolbar-height` for first-level
  section and column headings, `--region-inset` for panel interiors and
  `--page-inset` for horizontal insets. Chrome must size itself from them rather
  than from fixed pixel paddings, so every route keeps the same density and the
  remaining height belongs to operational content.
- Overflow belongs to bounded lists, tables, diagrams, inspectors or dialogs.
  Do not merely hide excess content: all controls and content must remain reachable
  through internal scrolling, reflow or zoom. Toolbars may scroll internally when
  their actions cannot fit. Keep header and footer inside the window.
- Workspace shows a single workflow stage. The graph is centered in its frame and
  auto-fits the measured content box through `ResizeObserver`, including changes
  caused by banners and navigation; there is no pannable canvas or manual zoom.
- Intake's source and task lists scroll independently. Columns reflow into rows in
  narrow windows. Its diagram fits the available region, with internal scrolling
  at the minimum readable scale or when zoomed. Reset returns to the fitted scale.
- Verify all routes at wide, standard, short and narrow window sizes, including
  long content, notifications, zoom and dialogs. Checking body overflow alone is
  insufficient: internal panels must have usable space and reachable controls.

## Routes and state lifetime

- Empty hash, `#workflow`, or an unrecognized hash (including the legacy
  `#tasks`) opens Workspace workflow.
- `#source-mapping` retains the existing Intake deep link.
- Hash changes drive browser back/forward and active rail state.
- Workspace stays mounted on every route, preserving and synchronizing the global
  Student/Campaign scope. It renders no DOM while another route is active.
- Intake and Review mount when entered and unmount when left. Filters and transient
  review markings reset on navigation; imported sources and Core mutations persist.

## Core integration

Pages import `core` and report types from `src/core/`. The command/argument/result
contract matches the existing Python UI allowlist. Callers cannot choose an
arbitrary response type or mix a command with another command's arguments.
Transport remains same-origin JSON POST to `/api/core`; Vite still owns the private
stdio bridge. HTTP, transport and Core errors remain visible to the caller.
TypeScript models describe the bridge payload; they are not runtime validation of
untrusted data. Backend validation and the allowlist remain authoritative.

Preparation readiness, deterministic intake, duplicate checks, confirmation
invalidation, Rewrite eligibility, reconciliation and external action authority
remain in Core. Intake transports selected bytes to an allowlisted command; Core
validates supported patterns and persists Source Materials. See
[workflow and bridge details](frontend-workflow.md).

## Verification

`npm test` checks route compatibility and Core transport success/failure behavior
using Node's built-in test runner (Node 24 or newer). `npm run build` checks all page
imports and TypeScript contracts. `npm run lint` checks the frontend source.
`python -m unittest tests.test_ui` exercises the actual persisted bridge contract.
Browser checks cover navigation history, page state lifetime, campaign dialogs,
Intake filtering/validation/inspection and responsive viewport containment.
For the repeatable browser check, open the dev server in a Playwright CLI session
against an isolated Core store, then run from the repository root:

```powershell
npx --yes --package @playwright/cli playwright-cli -s=layout open http://127.0.0.1:5179
npx --yes --package @playwright/cli playwright-cli -s=layout run-code --filename frontend/tests/viewport.browser.js
```

The check covers Workflow and Intake across seven sizes from 390×844 to
1920×1080, including 900×450. It checks bounded page dimensions and visible internal
regions; screenshots and interaction checks complement the geometry assertions.
