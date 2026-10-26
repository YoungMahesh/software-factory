# Map: Instant Cold Starts and Visual Multimodal QA for Factory Studio

## Spec
- Spec: `.scratch/studio-cold-starts-and-visual-qa/spec.md`
- Integration Branch: `feat/studio-cold-starts-and-visual-qa`

## Tickets
1. `01-automatic-filesystem-snapshot-capture-on-serving-state.md` (Blocked by: None)
2. `02-fast-path-sandbox-resumption-for-instant-cold-starts.md` (Blocked by: 01)
3. `03-in-sandbox-headless-visual-qa-and-console-crash-detection.md` (Blocked by: None)
4. `04-delivery-gate-visual-telemetry-and-preview-badge.md` (Blocked by: 03)

## Decisions so far
- Initial exploration notes saved at `/root/exploration-notes/studio-cold-starts-and-visual-qa/notes.md`.
- Universal file line budget ratchet (ADR 0051 & 0057): strict <= 500 lines for all production and test files.
- Dist freshness mandate: `pnpm --dir factory/ui/frontend build` must be run whenever frontend source files change.
