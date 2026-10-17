# 04: Diagnostic Summary Export, ADR, and Production Bundle

**What to build:** A "Copy Summary" diagnostic export control that copies a markdown table of top bottlenecks to the developer's clipboard, formal recording of ADR 0061, canonical domain glossary updates in `CONTEXT.md`, and compilation of the production frontend bundle into `factory/ui/static/dist/`.

**Blocked by:** 02: Infrastructure Badges, Stage Filtering, and Output Expansion, 03: Repository-Wide Telemetry Aggregation Endpoint and View

**Status:** ready-for-agent

- [ ] A "Copy Summary" button (`id="btn-copy-bottlenecks-summary"`) formats the active bottleneck list into a clean GitHub-flavored markdown table and copies it to the clipboard.
- [ ] Visual feedback confirms successful copying (changing icon/text to "Copied" for 2 seconds).
- [ ] Accepted ADR 0061 is committed at `docs/adr/0061-agent-command-bottleneck-profiler-and-telemetry-diagnostics.md`.
- [ ] `CONTEXT.md` is updated with the canonical terms `Agent Bottleneck Profiler` and `Infrastructure Bottleneck Heuristics`.
- [ ] Frontend production bundle is compiled via `pnpm --dir factory/ui/frontend build` into `factory/ui/static/dist/`.
- [ ] Automated tests, including `test_frontend_dist_freshness.py` and universal line budget ratchet tests, pass with zero uncommitted diffs.
