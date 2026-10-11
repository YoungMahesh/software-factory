# 02: In-Studio Grilling Assistant and Conversational Turn Service

**What to build:**
A fast, stateless conversational grilling service in Factory Studio that intercepts developer prompts, interviews the developer using structured question rounds with recommended answers, sharpens domain terminology against `CONTEXT.md`, and drafts lightweight Architectural Decision Records (ADRs) before any cloud sandbox or assembly line job is dispatched.

**Blocked by:** 01: Target Repository Scaffolding and Assembly Line ADR Quality Gate

**Status:** done

- [x] Implement a conversational Grilling Assistant service using OpenCode Go with system prompts embedding `grilling` and `domain-modeling` protocols.
- [x] Provide structured question round generation (`❓ Q1 ... ➡️ recommended answer`) identifying unsettled prerequisites on the requirement frontier.
- [x] Implement domain term sharpening against `CONTEXT.md` and automated draft ADR synthesis when architectural trade-offs are identified.
- [x] Update `POST /api/studio/prompt` to accept client chat history and a grill mode parameter, returning structured interview turns or a `ready_for_approval` state without launching sandboxes.
- [x] Provide deterministic mock mode for offline execution and automated test suites when API keys are absent.
- [x] Automated tests verify interview round progression, domain term sharpening, and draft ADR generation.

