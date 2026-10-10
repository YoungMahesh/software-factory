# 03: Fast Intent Guard and Conversational Ticket Orchestration

**What to build:** An API endpoint that ingests user prompts, evaluates them with a fast pre-flight intent classification guard, strictly refuses requests requiring non-frontend or backend functionality (databases, backend APIs, server storage) with an explicit explanation, and for valid frontend prompts, automatically synthesizes GitHub Milestones and sequential Issues under the target repository before dispatching an autonomous assembly line job.

**Blocked by:** 01: Dedicated Port 3010 and HTTP Basic Auth Security, 02: TanStack Start Template Repository Provisioning

**Status:** resolved

- [x] Prompts containing backend, database, server API, or external storage requirements are intercepted before sandbox provisioning and returned with a strict refusal message explaining the frontend-only boundary.
- [x] Valid frontend prompts automatically create or resolve Milestone `v1: Initial App` (or the active milestone) and sequential GitHub Issues (`#1`, `#2`...) under the target repository via GitHub API.
- [x] Synthesized issues include clear acceptance criteria and ticket specifications derived from the user's prompt.
- [x] Dispatches the autonomous assembly line job targeting the synthesized issue on branch `factory/<milestone>` through the in-memory job registry.
- [x] Returns job metadata, synthesized issue reference, and stage tracking information to the caller.
- [x] Automated tests verify that backend prompts are rejected without dispatching jobs, and frontend prompts generate appropriate milestone, issue, and job records.

## Answer

Resolved by implementing fast intent classification guardrail and conversational ticket lifecycle orchestration:

1. **Fast Intent Classification Guard (`factory/ui/guard.py`)**:
   - Implemented `evaluate_prompt_intent(prompt: str)` detecting out-of-scope backend requests (databases, backend servers/APIs, cloud/server storage) before sandbox or GitHub provisioning.
   - Preserves safe client-side browser mechanisms (such as `localStorage`, `sessionStorage`, `IndexedDB`, client-side mock fixtures).
   - Generates explicit, strict refusal messages detailing the frontend-only TanStack Start boundary and guiding developers to refine their requests.
2. **Milestone and Ticket Synthesis (`factory/ui/github.py`)**:
   - Implemented `normalize_milestone_slug(title: str)` producing consistent canonical slugs (e.g. `v1: Initial App` -> `v1-initial-app`).
   - Implemented `create_repo_milestone` and `resolve_or_create_milestone` querying and reusing active milestones or creating `v1: Initial App` via GitHub API.
   - Implemented `synthesize_ticket_content` converting prompt intent into structured ticket specifications with sequential titles (`01: ...`, `02: ...`), explicit dependency chains (`Blocked by: None` or `Blocked by: #<prev>`), `factory:ready` status, and actionable acceptance criteria.
   - Implemented `create_repo_issue` and `synthesize_and_create_issue` creating sequential GitHub issues under the active milestone.
3. **Conversational Prompt Orchestration Endpoints (`factory/ui/app.py`)**:
   - Added `POST /api/studio/prompt` (and alias `POST /api/prompt`) accepting `StudioPromptRequest` (`repo`, `prompt`, `model`, `vm`, `milestone_title`).
   - Rejects backend/database requests immediately with refusal payload and no compute/job provisioning.
   - For valid frontend prompts, resolves/creates the milestone, synthesizes sequential issues, and dispatches the autonomous assembly line job targeting the issue on branch `factory/<milestone>`.
   - Returns job metadata, synthesized issue reference, milestone information, and stage tracking status to the caller.
4. **Automated Unit & Integration Tests (`tests/test_ui.py`)**:
   - Added `TestFastIntentGuard` testing database, backend, storage, and allowed client-side prompts.
   - Added `TestTicketAndMilestoneSynthesis` testing initial and sequential ticket synthesis, milestone creation, and issue linking.
   - Added `TestConversationalPromptOrchestration` verifying API rejection payloads, valid job dispatch, sequential issue accumulation, route aliasing, and HTTP Basic Auth enforcement.
