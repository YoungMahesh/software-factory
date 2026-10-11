# Factory Studio Grilling Codebase Grounding and Error Resilience

**Status**: Accepted

To eliminate absurd recommendations (such as proposing brand-new page routes when developers ask to remove social media links), prevent silent failures, ground interview questions directly in target repository code facts, and avoid polluting repositories with trivial Architectural Decision Records, we decided to upgrade the Grilling Assistant with **Repository Codebase Grounding**, **Inference Error Turns**, a **Conditional ADR Policy**, and **Prompt Archetypes**.

## Considered Options

- **Blind Route Generation and Universal ADRs (Prior Behavior)**: Treating every user prompt as a request to create a new page route, and unconditionally drafting an ADR even for localized UI tweaks, link removals, or minor styling edits. Rejected because it confused developers, generated absurd route recommendations for component edits, and cluttered `docs/adr/` with non-architectural noise.
- **Silent Mock Fallback on Provider Failures**: Catching network or SSL errors silently and falling back to canned mock questions. Rejected because it masked infrastructure failures and misled developers into believing an offline mock was an active LLM reasoning turn.
- **Live Codebase Fact-Finding, Explicit Error Turns, Conditional ADRs, and Prompt Archetypes**:
  - Reconfiguring remote inference to connect directly to the canonical OpenCode Go API (`https://opencode.ai/zen/go/v1`).
  - Replacing silent fallback with explicit **Inference Error Turns** in the chat timeline, complete with error diagnostics and an interactive retry trigger.
  - Enabling autonomous **Repository Codebase Grounding** that inspects the remote repository's file tree on the active feature branch (`factory/<milestone>`) or `main`, identifies candidate components matching prompt keywords, and injects up to 25KB of candidate source code into the LLM system prompt.
  - Enforcing the "Offer ADRs sparingly" principle via a **Conditional ADR Policy**: drafting an ADR only when a change involves irreversible, fundamental architectural trade-offs, and setting `draft_adr` to null for localized component edits, deletions, or styling adjustments.
  - Implementing **Prompt Archetypes** (`deletion`, `component_modification`, `styling`, `new_feature`) to tailor offline mock heuristics and prevent route recommendations when modifying or deleting existing components.
  Accepted.

## Consequences

- The canonical terms **Repository Codebase Grounding**, **Conditional ADR Policy**, **Prompt Archetype**, and **Inference Error Turn** are incorporated into `CONTEXT.md`.
- **Inference Reliability**:
  - The Grilling Assistant points to `https://opencode.ai/zen/go/v1` and sends valid authentication headers.
  - Connection errors, timeouts, and HTTP status errors return structured error turns that are persisted to SQLite Studio Database (`chat_messages`) and render with retry actions.
- **Codebase Fact-Finding**:
  - The assistant discovers repository layout and candidate component sources (e.g. `Footer.tsx` for social link requests) before synthesizing interview questions.
  - Questions are grounded in existing components; proposing new routes is strictly forbidden for component modifications and deletions unless explicitly requested.
- **Conditional Architectural Decision Records**:
  - For localized component modifications, deletions, refactors, and styling adjustments, the assistant synthesizes implementation plans without drafting an ADR (`draft_adr: null`).
  - `ApprovalCard` renders implementation plans cleanly without broken ADR preview blocks when `draft_adr` is null.
  - Plan approval endpoint (`POST /api/studio/approve`) skips ADR commits and creates sequential GitHub issues cleanly when `draft_adr` is null.
- **Deterministic Offline Testing**:
  - Offline mock generator classifies prompts into archetypes (`deletion`, `component_modification`, `styling`, `new_feature`), generating realistic component-scoped questions and omitting ADRs for deletion and styling workflows.
