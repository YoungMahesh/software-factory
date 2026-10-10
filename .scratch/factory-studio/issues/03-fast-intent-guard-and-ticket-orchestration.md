# 03: Fast Intent Guard and Conversational Ticket Orchestration

**What to build:** An API endpoint that ingests user prompts, evaluates them with a fast pre-flight intent classification guard, strictly refuses requests requiring non-frontend or backend functionality (databases, backend APIs, server storage) with an explicit explanation, and for valid frontend prompts, automatically synthesizes GitHub Milestones and sequential Issues under the target repository before dispatching an autonomous assembly line job.

**Blocked by:** 01: Dedicated Port 3010 and HTTP Basic Auth Security, 02: TanStack Start Template Repository Provisioning

**Status:** ready-for-agent

- [ ] Prompts containing backend, database, server API, or external storage requirements are intercepted before sandbox provisioning and returned with a strict refusal message explaining the frontend-only boundary.
- [ ] Valid frontend prompts automatically create or resolve Milestone `v1: Initial App` (or the active milestone) and sequential GitHub Issues (`#1`, `#2`...) under the target repository via GitHub API.
- [ ] Synthesized issues include clear acceptance criteria and ticket specifications derived from the user's prompt.
- [ ] Dispatches the autonomous assembly line job targeting the synthesized issue on branch `factory/<milestone>` through the in-memory job registry.
- [ ] Returns job metadata, synthesized issue reference, and stage tracking information to the caller.
- [ ] Automated tests verify that backend prompts are rejected without dispatching jobs, and frontend prompts generate appropriate milestone, issue, and job records.
