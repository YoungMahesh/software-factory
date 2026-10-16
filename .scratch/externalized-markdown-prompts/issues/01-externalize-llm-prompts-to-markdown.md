# 01: Externalize Factory Studio Grilling and Assembly Line Agent Prompts to Markdown Files

**What to build:** Extract all hardcoded LLM system prompts used when creating and modifying applications in Factory Studio into separate, version-controlled `.md` files. This includes the Grilling Assistant system prompt (`factory/ui/grill/prompts/grilling_assistant.md`) and the Assembly Line agent system prompts (`sandbox/factory/harness/prompts/planner_system.md`, `coder_system.md`, and `reviewer_system.md`). Implement double-curly brace (`{{variable}}`) template substitution and on-demand in-memory caching in both the host Python service and the sandbox TypeScript harness, with strict `FileNotFoundError` validation on missing templates. Record the design decision in ADR 0056 and update the `CONTEXT.md` domain glossary.

**Blocked by:** None

**Status:** resolved

- [x] Create `factory/ui/grill/prompts/grilling_assistant.md` containing the Grilling Assistant persona, codebase grounding rules, TanStack Start client-side boundaries, conditional ADR policy, and JSON schemas with `{{variable}}` substitution tokens.
- [x] Create `sandbox/factory/harness/prompts/planner_system.md`, `coder_system.md`, and `reviewer_system.md` containing the specialized assembly line agent system prompts and JSON schemas.
- [x] Implement `factory/ui/grill/_prompts.py` with `load_prompt_template` and `render_prompt_template`, supporting regex-based `{{variable}}` substitution, in-memory caching, cache-bypassing, and explicit `FileNotFoundError` raising.
- [x] Update `build_system_instruction` in `factory/ui/grill/_inference.py` to render the system instruction using `render_prompt_template`.
- [x] Update `sandbox/factory/harness/prompts.ts` to load markdown prompt files from `sandbox/factory/harness/prompts/`, exporting loaded constants (`PLANNER_SYSTEM_PROMPT`, `CODER_SYSTEM_PROMPT`, `REVIEWER_SYSTEM_PROMPT`) with fallback/error handling.
- [x] Record Architectural Decision Record `docs/adr/0056-externalized-markdown-prompts-for-studio-and-assembly-line.md` and document `Externalized Prompt Templates` in `CONTEXT.md`.
- [x] Add and execute unit tests in `tests/test_grill.py` and `sandbox/factory/harness.test.ts` verifying template rendering, variable interpolation, cache behavior, and missing file error handling.

## Comments

Successfully externalized all Factory Studio Grilling and Assembly Line Agent prompts to version-controlled Markdown files with in-memory caching, double-curly brace substitution, and strict error handling:

1. **Host Python Grilling Prompts (`factory/ui/grill/`)**:
   - Created `factory/ui/grill/prompts/grilling_assistant.md` containing the Grilling Assistant persona, codebase grounding rules, client-side boundaries, conditional ADR policy, and JSON schemas with `{{variable}}` placeholders.
   - Implemented `factory/ui/grill/_prompts.py` providing `load_prompt_template` and `render_prompt_template` with in-memory caching, reload support, regex token substitution, and `FileNotFoundError` error handling.
   - Refactored `build_system_instruction` in `factory/ui/grill/_inference.py` to render using `render_prompt_template`, reducing the production file size by 60 lines.
   - Added unit test suite `TestPromptTemplates` in `tests/test_grill.py` verifying template loading, caching, reload bypass, variable substitution, and missing file exception handling.

2. **In-Sandbox Assembly Line Prompts (`sandbox/factory/harness/`)**:
   - Created `sandbox/factory/harness/prompts/planner_system.md`, `coder_system.md`, and `reviewer_system.md`.
   - Updated `sandbox/factory/harness/prompts.ts` with `loadPromptTemplate` and `renderPromptTemplate` supporting synchronous loading, in-memory caching, reload bypass, and descriptive error throwing on missing templates.
   - Maintained backward compatibility by exporting loaded constants `PLANNER_SYSTEM_PROMPT`, `CODER_SYSTEM_PROMPT`, and `REVIEWER_SYSTEM_PROMPT`.
   - Re-exported template utilities in `sandbox/factory/harness/index.ts`.
   - Added comprehensive unit tests in `sandbox/factory/harness.test.ts`.

3. **Architecture and Domain Documentation**:
   - Documented the canonical domain term **Externalized Prompt Templates** in `CONTEXT.md`.
   - Recorded ADR `docs/adr/0056-externalized-markdown-prompts-for-studio-and-assembly-line.md`.
