# 01: Target Repository Scaffolding and Assembly Line ADR Quality Gate

**What to build:**
Enable newly created and existing target repositories to automatically carry Matt Pocock's engineering skills, domain glossary, and architectural decision records (`docs/adr/`), and enforce architectural compliance as a mandatory quality gate in the assembly line pipeline so that AI models cannot introduce changes that contradict accepted ADRs.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] New repositories instantiated from `tanstack-start-template` are automatically scaffolded with `CONTEXT.md`, `docs/adr/0001-tanstack-start-spa-architecture.md`, `docs/agents/`, and core engineering skills in `.agents/skills/`.
- [ ] Provide a sync utility (`scripts/sync_target_repo_skills.py`) to backfill skills and ADR structures into existing test repositories.
- [ ] Pre-flight Guard validates that `docs/adr/` exists and contains at least one accepted ADR file, failing preflight if missing.
- [ ] Assembly Line Planner Agent receives all accepted ADR files in its planning context alongside `CONTEXT.md`.
- [ ] Assembly Line Reviewer Agent evaluates git diffs against accepted ADRs in `docs/adr/` under standards compliance, rejecting non-compliant diffs.
- [ ] Automated tests verify pre-flight guard behavior, ADR context ingestion, and reviewer rejection of ADR-violating diffs.
