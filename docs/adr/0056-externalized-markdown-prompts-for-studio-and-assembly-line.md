# Externalized Markdown Prompts for Studio and Assembly Line

**Status**: Accepted (Amends [ADR 0025](0025-pi-agent-harness-and-stage-specialization.md) and [ADR 0040](0040-grill-with-docs-and-matt-pocock-skills-in-factory-studio.md))

To improve prompt engineering ergonomics, eliminate template escaping collisions with JSON schemas, prevent production code file bloat, and unify system prompt authoring conventions across both the host Python service and the sandbox TypeScript harness, we decided to externalize all LLM system prompts into dedicated, version-controlled markdown files.

## Considered Options

- **Inline Code String Constants (Status Quo)**: Retaining hardcoded multi-page prompt constants as Python f-strings in `factory/ui/grill/_inference.py` and TypeScript template literals in `sandbox/factory/harness/prompts.ts`. Rejected because inline strings directly conflict with single-brace `{}` JSON schema formatting (requiring double-brace escaping in Python), bloat application code files against the repository line budget ratchet (ADR 0051), and hinder prompt diffing and auditing in pull requests.
- **Remote Database or Cloud Prompt Management Registry**: Storing and fetching prompt templates dynamically from an external database or cloud prompt registry at runtime. Rejected because it introduces remote network dependencies during inference bootstrapping, complicates offline testing and local sandbox execution, and breaks the repository's principle of single-context, version-controlled artifacts.
- **Externalized Version-Controlled Markdown Files with Double-Curly Brace Substitution and In-Memory Caching**:
  1. Storing system prompts as standalone `.md` files colocated in their execution runtimes (`factory/ui/grill/prompts/grilling_assistant.md` for host Python Grilling, and `sandbox/factory/harness/prompts/` for sandbox TypeScript Assembly Line agents).
  2. Employing double-curly brace (`{{variable}}`) substitution for dynamic contextual values (`{{repo}}`, `{{context_content}}`, `{{existing_adrs}}`, `{{formatted_structure}}`, `{{formatted_sources}}`), leaving single-brace `{}` JSON schemas completely untouched and unescaped.
  3. Caching templates in memory on first access to eliminate repeated disk I/O, while providing reload options for testing.
  4. Enforcing strict error handling that immediately raises descriptive errors (`FileNotFoundError` in Python, descriptive `Error` in TypeScript) if a template file is missing.
  Accepted because it decouples prompt engineering from application code, protects container mounting boundaries without Dockerfile changes, avoids JSON formatting collisions, and reduces production code file line counts.

## Consequences

- The canonical domain term **Externalized Prompt Templates** is recorded in `CONTEXT.md`.
- `factory/ui/grill/prompts/grilling_assistant.md` contains the Grilling Assistant persona, codebase grounding rules, TanStack Start client-side boundaries, conditional ADR policy, and JSON schemas.
- `sandbox/factory/harness/prompts/planner_system.md`, `coder_system.md`, and `reviewer_system.md` contain specialized assembly line agent system prompts.
- `factory/ui/grill/_prompts.py` exports `load_prompt_template` and `render_prompt_template` with in-memory caching and regex substitution.
- `factory/ui/grill/_inference.py` constructs system instructions using `render_prompt_template`, reducing file size well within line budget limits.
- `sandbox/factory/harness/prompts.ts` exports `loadPromptTemplate`, `renderPromptTemplate`, and loads `PLANNER_SYSTEM_PROMPT`, `CODER_SYSTEM_PROMPT`, and `REVIEWER_SYSTEM_PROMPT` from markdown.
- Unit test suites in `tests/test_grill.py` and `sandbox/factory/harness.test.ts` verify template loading, caching, variable substitution, and missing file error handling.
