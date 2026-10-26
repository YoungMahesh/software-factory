# Map: Instant Cold Starts and Visual Multimodal QA for Factory Studio

## Spec
- Spec: `.scratch/studio-cold-starts-and-visual-qa/spec.md`
- Integration Branch: `feat/studio-cold-starts-and-visual-qa`

## Tickets
1. `01-automatic-filesystem-snapshot-capture-on-serving-state.md` (Status: resolved)
2. `02-fast-path-sandbox-resumption-for-instant-cold-starts.md` (Blocked by: 01)
3. `03-in-sandbox-headless-visual-qa-and-console-crash-detection.md` (Status: resolved)
4. `04-delivery-gate-visual-telemetry-and-preview-badge.md` (Status: resolved)

## Decisions so far
- Initial exploration notes saved at `/root/exploration-notes/studio-cold-starts-and-visual-qa/notes.md`.
- Universal file line budget ratchet (ADR 0051 & 0057): strict <= 500 lines for all production and test files.
- Dist freshness mandate: `pnpm --dir factory/ui/frontend build` must be run whenever frontend source files change.
- Ticket 01 resolved: Implemented non-destructive filesystem snapshot capture on transition to `PreviewStage.SERVING` with 30-day TTL, database schema extension and metadata persistence in `factory/ui/db`, background execution in `factory/ui/registry/_snapshot.py`, and test coverage in `tests/test_ui_db.py` and `tests/test_preview/test_snapshot.py`.
- Ticket 03 resolved: Implemented in-sandbox headless visual QA verification using Playwright and pre-baked Google Chrome (`sandbox/factory/visual-qa.ts`), enforcing Clean Canvas Invariant, trapping fatal browser runtime errors/console errors for self-correction feedback, capturing desktop (1280x800) and mobile (390x844) viewport screenshots, emitting `__SF_EVENT__:{"type":"visual_qa",...}` telemetry, integrated into pipeline lifecycle (`sandbox/factory/lifecycle.ts`), with full unit and E2E test coverage in `sandbox/factory/visual-qa.test.ts`.
- Ticket 04 resolved: Implemented backend REST endpoints (`GET /api/studio/repos/{repo}/visual-qa` and `/api/studio/repos/{repo}/visual-qa/screenshot` along with `/api/repos/{repo}/...` canonical aliases) to serve visual verification metadata and viewport screenshots. Updated web frontend `DeliveryGateCard` to display `VisualQABadge` alongside deterministic verdicts, rendered `VisualQAThumbnail` with desktop and mobile capture indicators, integrated expandable `VisualQAModal` with high-resolution screenshot preview and viewport toggling, blocked squash merge controls upon visual verification failures with warning telemetry, and decomposed subcomponents to strictly obey the 500-line budget. Full test coverage in `tests/test_ui/test_visual_qa_api.py` and `DeliveryGateVisualQA.test.tsx`.
