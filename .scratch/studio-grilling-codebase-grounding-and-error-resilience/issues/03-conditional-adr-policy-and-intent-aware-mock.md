# 03: Conditional ADR Policy and Archetype-Aware Mock Heuristics

**What to build:** Enforce the "Offer ADRs sparingly" principle by making Architectural Decision Record generation conditional on genuine architectural impact, and upgrade the offline mock generator with intent-aware archetypes. For minor component modifications, deletions, or styling adjustments, the assistant synthesizes implementation plans without drafting an ADR, and the UI plan card renders cleanly without broken ADR previews. In offline mock mode, the generator classifies requests into archetypes (`deletion`, `component_modification`, `styling`, `new_feature`) to produce realistic questions. Also updates domain documentation in `CONTEXT.md` and records ADR 0043.

**Blocked by:** 02 (Repository Codebase Grounding and Source Context Ingestion)

**Status:** ready-for-agent

- [ ] LLM system prompt instructs the assistant to draft an ADR only when the change introduces irreversible, significant architectural trade-offs, setting `draft_adr` to null for localized component edits and deletions.
- [ ] Turn result model and parser support null `draft_adr` values during `ready_for_approval` turns.
- [ ] Factory Studio plan approval card displays implementation plans and issue targets cleanly without broken ADR preview blocks when `draft_adr` is null.
- [ ] Offline mock generator classifies prompt archetypes, generating component-scoped questions for deletions (e.g. removing links) without recommending new routes or ADRs.
- [ ] Domain definition in `CONTEXT.md` is updated and `docs/adr/0043-factory-studio-grilling-codebase-grounding-and-error-resilience.md` is recorded.
- [ ] Unit and endpoint test suites verify error turns, codebase grounding, conditional ADRs, and archetype-aware mock turns.
