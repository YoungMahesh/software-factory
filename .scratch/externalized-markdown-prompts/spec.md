# Spec: Externalized Markdown Prompts for Factory Studio and Assembly Line Agents

Status: resolved
Triage: resolved

## Problem Statement

When creating or modifying applications in Factory Studio, prompts sent to LLMs are currently hardcoded as embedded Python f-string constants in `factory/ui/grill/_inference.py` and TypeScript template literal constants in `sandbox/factory/harness/prompts.ts`.

Hardcoded inline prompts present multiple architectural and operational problems:
1. **Difficult Prompt Engineering and Auditability**: System prompts define extensive persona instructions, domain constraints, client-side boundaries, and strict JSON output schemas. Reading, editing, and diffing multi-page prompt strings inside Python and TypeScript code files is cumbersome and prone to accidental syntax regressions.
2. **Template Collision with JSON Schemas**: Standard string interpolation (such as Python f-strings or single-curly brace formatters) directly conflicts with single-brace `{}` JSON schema syntax, requiring awkward character escaping and risking runtime formatting exceptions.
3. **Bloated Production Code Files**: Inline prompt constants inflate code files by hundreds of lines, creating friction with repository line budget constraints (ADR 0051 / `AGENTS.md`).
4. **Scattered Prompt Definitions Across Tiers**: The system prompt for the Grilling Assistant (interactive requirement alignment) and the system prompts for the Assembly Line Pipeline agents (Planner, Coder, and Reviewer) follow different formatting and storage conventions, lacking a unified markdown standard.

## Solution

Externalize all LLM system prompts into dedicated, standalone `.md` files colocated within their respective execution runtime directories, powered by a lightweight `{{variable}}` double-curly brace template substitution engine and on-demand in-memory caching:

1. **Dedicated Markdown Prompt Files**:
   - `factory/ui/grill/prompts/grilling_assistant.md`: Single comprehensive markdown document specifying Grilling Assistant persona, grounding rules, TanStack Start client-side boundaries, conditional ADR policy, and JSON output schemas.
   - `sandbox/factory/harness/prompts/planner_system.md`: Planner Agent persona, read-only constraints, and JSON plan schema.
   - `sandbox/factory/harness/prompts/coder_system.md`: Coder Agent persona, code generation rules, and self-correction instructions.
   - `sandbox/factory/harness/prompts/reviewer_system.md`: Reviewer Agent persona, read-only diff inspection rules, ADR compliance enforcement, and JSON review verdict schema.

2. **Double-Curly Brace Substitution (`{{variable}}`)**:
   - Dynamic contextual values (`{{repo}}`, `{{context_content}}`, `{{existing_adrs}}`, `{{formatted_structure}}`, `{{formatted_sources}}`) are interpolated via double-curly braces.
   - Single braces `{}` within JSON schemas, TypeScript types, and code snippets remain completely unescaped and untouched.

3. **Colocated Runtime Storage**:
   - Host Python Grilling prompts reside in `factory/ui/grill/prompts/`.
   - Sandbox TypeScript agent prompts reside in `sandbox/factory/harness/prompts/`.
   - This preserves container filesystem boundaries: `sandbox/factory/` is mounted into `/root/factory` inside the Modal sandbox without requiring container build modifications.

4. **On-Demand In-Memory Caching with Strict Error Handling**:
   - Template files are loaded on demand and cached in memory to eliminate repeated disk I/O in production.
   - An optional reload / cache-clear flag is provided for testing and prompt iteration.
   - Missing or unreadable template files raise an explicit, descriptive error (`FileNotFoundError` in Python, descriptive `Error` in TypeScript) rather than silently falling back to stale defaults.

5. **Domain Documentation**:
   - Incorporate the canonical definition of **Externalized Prompt Templates** into `CONTEXT.md`.
   - Record the architectural decision in `docs/adr/0056-externalized-markdown-prompts-for-studio-and-assembly-line.md`.

## User Stories

1. As a prompt engineer, I want to edit the Grilling Assistant system prompt directly in `grilling_assistant.md`, so that I can refine interview behavior and tone without editing Python application code.
2. As a prompt engineer, I want to edit the Planner Agent system prompt in `planner_system.md`, so that I can update implementation planning rules and JSON plan schemas cleanly.
3. As a prompt engineer, I want to edit the Coder Agent system prompt in `coder_system.md`, so that I can clarify coding constraints and reproduction test instructions.
4. As a prompt engineer, I want to edit the Reviewer Agent system prompt in `reviewer_system.md`, so that I can sharpen ADR compliance checks and review verdict criteria.
5. As a developer, I want prompt templates to use `{{variable}}` syntax, so that single braces in JSON schemas and code snippets are never mangled by template substitution.
6. As a developer modifying `grilling_assistant.md`, I want dynamic repository variables (`{{repo}}`, `{{context_content}}`, `{{existing_adrs}}`, `{{formatted_structure}}`, `{{formatted_sources}}`) to be reliably substituted at runtime.
7. As a backend developer, I want prompt templates to be cached in memory on first access, so that disk I/O overhead is eliminated during high-frequency chat turns.
8. As a test author, I want to be able to reload or bypass the prompt template cache in tests, so that test scenarios can verify template modifications and isolate test state.
9. As a developer or CI runner, if a prompt template file is missing from the filesystem, I want an immediate, descriptive error explaining the exact missing path, so that misconfigurations are detected before LLM inference begins.
10. As a developer inspecting the repo, I want prompt files colocated with their execution tier (`factory/ui/grill/prompts/` and `sandbox/factory/harness/prompts/`), so that container mounting boundaries in `factory/spawner/_config.py` remain clean and untouched.
11. As a developer using the TypeScript harness in the sandbox, I want existing exports (`PLANNER_SYSTEM_PROMPT`, etc.) to continue to work transparently, so that existing runner pipelines do not break.
12. As a software factory maintainer, I want the externalized prompt pattern documented in `CONTEXT.md` and recorded in an ADR, so that the domain glossary and architectural history remain accurate.
13. As a developer, I want the Grilling Assistant prompt in `_inference.py` to be extracted to markdown, helping keep production Python files well within the repository line budget ratchet.
14. As an assembly line agent, I want clear Markdown formatting in system prompts, so that model context reasoning deltas follow clean section semantics.
15. As a reviewer agent, I want prompt definitions tracked in version control as standard markdown documents, so that prompt diffs in pull requests are easy to review and compare.

## Implementation Decisions

- **Dedicated Template Modules**:
  - Python: A dedicated internal module `factory/ui/grill/_prompts.py` will provide `load_prompt_template(name: str, reload: bool = False) -> str` and `render_prompt_template(name: str, variables: dict[str, Any], reload: bool = False) -> str`.
  - TypeScript: `sandbox/factory/harness/prompts.ts` will provide `loadPromptTemplate(name: string, reload?: boolean): string` and continue exporting `PLANNER_SYSTEM_PROMPT`, `CODER_SYSTEM_PROMPT`, and `REVIEWER_SYSTEM_PROMPT` loaded from markdown.
- **Substitution Engine**:
  - Python: Uses regex replacement `re.sub(r"\{\{([a-zA-Z0-9_]+)\}\}", ...)` to cleanly interpolate variables without formatting collisions.
  - TypeScript: Uses regex replacement `template.replace(/\{\{([a-zA-Z0-9_]+)\}\}/g, ...)` where needed.
- **System vs. User Prompt Boundary**:
  - System prompts (persona, constraints, JSON schemas) are externalized to `.md` files.
  - User prompt construction (which conditionally bundles tickets, plans, diagnostics, and diffs) remains programmatic in `runner.ts`.
- **Packaging and Sandbox Mounts**:
  - `sandbox/factory/` is already mounted to `/root/factory` in `build_factory_image`, so `sandbox/factory/harness/prompts/` is automatically packaged into sandboxes without container build changes.
  - `factory/ui/grill/prompts/` lives directly in the host package tree.

## Testing Decisions

- **Test Seam**:
  The primary test seams are:
  1. Python Seam: `tests/test_grill.py` asserting that `build_system_instruction` correctly renders from `grilling_assistant.md`, substitutes all variables, caches appropriately, and raises `FileNotFoundError` on missing templates.
  2. TypeScript Seam: `sandbox/factory/harness.test.ts` asserting that `PLANNER_SYSTEM_PROMPT`, `CODER_SYSTEM_PROMPT`, and `REVIEWER_SYSTEM_PROMPT` are successfully loaded from their markdown files and contain the required personas and JSON schemas.
- **Tested Modules**:
  - `factory/ui/grill/_prompts.py`
  - `factory/ui/grill/_inference.py`
  - `sandbox/factory/harness/prompts.ts`
  - `sandbox/factory/harness/runner.ts`
- **Prior Art**:
  Existing test suites in `tests/test_grill.py` and `sandbox/factory/harness.test.ts`.

## Out of Scope

- Externalizing dynamic runtime user prompt assembly (e.g. conditional self-correction diagnostic blocks in `runner.ts`).
- Storing or fetching prompt templates from remote cloud databases or external APIs (templates are version-controlled in the repository).
- Modifying deterministic issue title synthesis heuristics in `factory/ui/github/_issues.py`.

## Further Notes

- All modified and new production files adhere to the <= 500 line budget rule in `AGENTS.md`.
