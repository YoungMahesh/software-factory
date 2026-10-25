# Factory Studio Redundancy Removal and Chrome Consolidation

**Status**: Accepted (Amends [ADR 0048](0048-live-preview-branch-selector-and-in-place-switching.md), [ADR 0050](0050-studio-turn-rollback-and-in-place-reversion.md), [ADR 0052](0052-unified-studio-sandbox-and-simplified-web-lifecycle.md), and [ADR 0059](0059-consolidate-testing-console-into-factory-studio-and-canonicalize-api-routes.md))

To streamline Factory Studio, eliminate visual chrome duplication, and excise vestigial testing console and filesystem tracker residue, we decided to:

1. **Delete Dead Testing Console & Filesystem Tracker Residue**:
   - Excise `StageStepper.tsx` and its test (`StageStepper.test.tsx`), orphaned following the retirement of `TestingConsoleView.tsx` in ADR 0059.
   - Remove `launchJob()` from `api.ts` and excise `POST /api/jobs` from `factory/ui/routes/jobs.py`, canonicalizing all job dispatches on `/api/dispatch` and `/api/approve`.
   - Remove `factory/ui/tracker.py` and its calls from `factory/ui/routes/rollback.py`, standardizing all rollback operations exclusively on GitHub Issues without searching for legacy `.scratch/` markdown files.
   - Remove the `redirectConsolePath()` router redirect in `App.tsx`.

2. **Deduplicate Studio Header and Preview Toolbar Chrome**:
   - Remove the standalone red Stop button (`#btn-studio-preview-stop`) from `StudioHeader.tsx`. Retain the start/stop toggle on the "Preview App" button in `StudioHeader.tsx` and the dedicated Stop button in `LivePreviewToolbar.tsx`.
   - Canonicalize Turn Rollback to `PromptComposer.tsx` (`#btn-composer-rollback`) colocated with chat turn entry; remove the duplicate `#btn-preview-rollback` button from `LivePreviewToolbar.tsx`.
   - Remove duplicate rollback prop drilling through `StudioPreviewPane.tsx` and `LivePreview.tsx`.

3. **Eliminate Duplicate State and Query Invalidation**:
   - Remove `isLocalIssueDrawerOpen` from `StudioView.tsx`, binding directly to `isIssueDrawerOpen` in `StudioContext`.
   - Consolidate query cache invalidation so `App.tsx` handles issues cache invalidation while `StudioView.tsx` handles branch cache invalidation, eliminating duplicate network refetches.
   - Remove redundant local fallback hooks for `branchesQuery` and `updateBranchMutation` in `StudioView.tsx`.

4. **Modernize Activity Drawer Logging**:
   - Upgrade the "Logs" tab in `ActivityDrawer.tsx` to render `TerminalLogViewer` (providing virtualized line rendering, autoscroll toggling, and copy controls) rather than raw string concatenation.
   - Retain the collapsible bottom drawer in `LivePreview.tsx` for immediate inline preview startup error inspection.

## Considered Options

- **Rollback in Toolbar vs Composer**: Placing rollback in both locations created UI clutter and duplicated disabled/locking logic. Placing rollback strictly in `PromptComposer` anchors turn undo directly beside the conversational prompt interface where turns are created.
- **Stop Button Consolidation**: Having three stop buttons (two in `StudioHeader` and one in `LivePreviewToolbar`) was redundant. Keeping the "Preview App" toggle button and the canvas toolbar stop button ensures controls are always within reach without occupying redundant header space.

## Consequences

- **Universal File Line Budget Compliance**: All created and modified files remain strictly <= 500 lines.
- **Bundle Freshness**: The compiled production bundle in `factory/ui/static/dist/` is rebuilt via `pnpm build`.
- **Domain Glossary**: Deprecated references to `tracker.py` and Testing Console `StageStepper` are purged.
