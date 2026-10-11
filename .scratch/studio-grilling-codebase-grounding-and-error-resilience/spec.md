# Spec: Factory Studio Grilling Codebase Grounding and Error Resilience

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

When a developer in Factory Studio opens a repository and submits a prompt with "Grill & Align" enabled to clarify or modify code (such as "remove social media links like github, x.com, etc"), the Grilling Assistant generates irrelevant and absurd recommendations. Specifically, instead of addressing the developer's requested modification against existing UI components, the assistant immediately asks where in the application route tree the feature should be mounted and recommends creating a brand-new page route named after the prompt slug (e.g. `app/routes/remove-social-media-links-like-github-xcom-etc.tsx`).

This behavior is caused by four underlying failures:
1. **Inference Provider Connectivity Failure**: The conversational grilling service is configured with an invalid OpenCode Go endpoint URL that fails SSL certificate verification.
2. **Silent Failure and Instant Mock Fallback**: When live inference fails, network exceptions are caught and swallowed silently without alerting the developer, instantaneously falling back to an offline mock generator.
3. **Hardcoded Route Assumption in Mock Generator**: The offline mock generator blindly assumes every user prompt is an instruction to create a new page, slugifying the prompt and asking canned questions about route placement and client state stores.
4. **Lack of Codebase Grounding in Grilling Protocol**: The grilling service does not inspect the target repository's file tree or existing source code files before generating questions, violating the Matt Pocock grilling principle that finding facts is the agent's job and leaving the LLM blind to the actual component structure.
5. **Indiscriminate ADR Generation**: The system attempts to draft an Architectural Decision Record (ADR) for every request, even minor UI component modifications, deletions, or styling adjustments that do not involve significant architectural trade-offs.

## Solution

Upgrade the Factory Studio Grilling Assistant and the Grill-Before-Change Protocol to ground requirement alignment directly in target repository code facts, surface inference errors transparently, draft ADRs conditionally, and provide archetype-aware mock heuristics:

1. **Canonical OpenCode Go Provider Endpoint**:
   - Reconfigure the Grilling Assistant inference service to communicate with the canonical OpenCode Go API endpoint (`https://opencode.ai/zen/go/v1`).
   - Validate API tokens and request headers adhering to standard OpenCode Go formats.

2. **Transparent Error Surfacing**:
   - Eliminate silent mock fallbacks during live conversational turns.
   - When a remote inference failure occurs (network timeout, connection drop, SSL error, authentication rejection), return an explicit error turn.
   - Record the error turn in Studio Chat History and display an error alert callout in the studio chat timeline with diagnostic details and a retry button.
   - Restrict the offline mock generator strictly to explicit mock execution (e.g. unit testing).

3. **Autonomous Repository Codebase Grounding**:
   - Before synthesizing question frontiers or plans, the Grilling Assistant autonomously discovers codebase facts from the target repository via the GitHub API.
   - The assistant inspects the active feature branch (`factory/<milestone>`) if present on remote, falling back to `main`.
   - The assistant retrieves the recursive repository file tree to understand existing route structures and component organization.
   - The assistant scores file paths against keywords extracted from the user's prompt (e.g. `links`, `social`, `footer`, `header`, `nav`), ingests the raw content of up to three top candidate files, and injects both the repository structure and candidate source code into the LLM system prompt.

4. **Conditional ADR Drafting ("Offer ADRs Sparingly")**:
   - Instruct the LLM system prompt to evaluate architectural impact adhering to the domain modeling protocol.
   - Architectural Decision Records (`docs/adr/`) are only proposed when a change involves irreversible, fundamental trade-offs (e.g. introducing new routing paradigms, external storage, state management libraries, or third-party service architectures).
   - For localized component modifications, deletions, refactors, bug fixes, or styling changes, set `draft_adr` to null and synthesize only the implementation plan and issue specification.

5. **Archetype-Aware Mock Heuristics for Offline Testing**:
   - Replace the rigid "new route" assumption in the mock generator with prompt archetype classification (`deletion`, `component_modification`, `styling`, `new_feature`).
   - When handling deletions (e.g. removing links), generate realistic questions regarding component scope and layout reflow without inventing new routes or unnecessary ADRs.

## User Stories

1. As a developer in Factory Studio asking to remove social media links, I want the Grilling Assistant to understand where those links currently exist in my components, so that I am asked relevant questions rather than being prompted to create a new page.
2. As a developer submitting a prompt with "Grill & Align" enabled, I want the assistant to inspect my repository's existing file tree and relevant components before questioning me, so that questions are grounded in actual codebase facts.
3. As a developer modifying code on an active feature branch, I want the Grilling Assistant to inspect the latest cumulative code on that branch, so that recent changes from prior tickets are considered during the interview.
4. As a developer in Factory Studio, I want live conversational grilling to connect to the valid OpenCode Go inference endpoint, so that my prompts are evaluated by live LLM reasoning rather than offline static templates.
5. As a developer using Factory Studio when the LLM service or network is unavailable, I want to see a clear error banner in the chat timeline explaining the failure, so that I know why my prompt was not processed.
6. As a developer encountering an inference error, I want an immediate "Retry" option in the chat timeline, so that I can re-attempt the turn without re-typing my prompt.
7. As a developer, I do not want remote inference errors to silently fail over to hardcoded mock questions, so that I am never confused by synthetic or misleading responses.
8. As a developer making a simple UI tweak (like removing links or modifying styling), I want the Grilling Assistant to produce an implementation plan without drafting an ADR, so that my repository's `docs/adr/` directory is not polluted with trivial decisions.
9. As a developer introducing a major architectural change (such as adding a new database or client-server state library), I want the Grilling Assistant to draft a formal ADR, so that long-term architectural decisions are documented.
10. As a developer reviewing an approved plan for a minor modification without an ADR, I want the approval card to display the implementation plan and target issue clearly without broken ADR preview links, so that I can approve the build with confidence.
11. As a developer running offline tests with mock mode enabled, I want the mock generator to recognize deletion requests and ask about component scope, so that offline tests mirror realistic developer workflows.
12. As a developer running offline tests for a new feature request, I want the mock generator to ask about route placement and state management, so that new feature workflows remain deterministically tested.
13. As a developer reviewing Grilling Assistant questions, I want each question to provide numbered IDs, concise titles, clear questions, and recommended answers, so that I can easily answer by accepting defaults or customizing specific points.
14. As a developer answering a question frontier, I want settled decisions to advance the conversation toward plan synthesis, so that requirements are sharpened quickly.
15. As a developer reviewing chat history after an interview, I want question frontiers, error states, and finalized plans to be durably persisted across browser refreshes, so that conversation context is never lost.

## Implementation Decisions

- **Inference Service Reconfiguration**:
  The Grilling Assistant configuration will be updated to point to the canonical OpenCode Go base URL and authenticate requests using resolved OpenCode credentials.
- **Error Turn Representation and Persistence**:
  A new turn type representing inference errors will be added to the grilling protocol result model. When remote inference throws an exception, the service will return this error turn instead of invoking mock routines. The studio conversation handler will record this error turn to the durable chat database and return it to the client.
- **Repository Codebase Fact-Finding Client**:
  A repository inspection client will be added to the grilling service. It will determine the active branch (milestone branch or default branch), query the Git Trees API for the full hierarchy of source files, match keywords from the user prompt against file paths, and fetch raw file bodies for the top candidate matches up to a conservative size budget.
- **Context Injection into Grilling Prompts**:
  The system instruction for live grilling turns will be updated to incorporate the repository layout overview and relevant component file contents under explicit sections. The system prompt will mandate that questions be grounded in existing components and forbid proposing new routes unless a new view is explicitly requested.
- **Conditional Architectural Decision Record Policy**:
  The system prompt instructions will explicitly enforce the rule that Architectural Decision Records are reserved for significant, irreversible architectural trade-offs. For non-architectural changes, the assistant will omit the draft ADR from its JSON output while retaining the implementation plan.
- **Intent Archetype Mock Classifier**:
  The offline mock implementation will inspect prompt patterns to classify requests into distinct archetypes. Deletion and modification archetypes will produce component-scoped questions and omit ADRs, while new feature archetypes will maintain routing and state questions.

## Testing Decisions

- **Test Seam**:
  The primary test seam is the studio prompt endpoint (`POST /api/studio/prompt`), which exercises the end-to-end integration including intent routing, grilling turn generation, database persistence, and response shaping. A secondary unit test seam directly verifies the grilling assistant service methods with mocked HTTP transports.
- **Tested Modules**:
  The conversational grilling service module, the GitHub discovery client module, and the studio prompt API router module.
- **Prior Art**:
  Existing isolated unit tests in `test_grill.py` and endpoint integration tests in `test_ui.py`.
- **Test Scenarios**:
  1. Live inference configuration targets the canonical OpenCode Go URL and sends valid headers.
  2. Network connection or inference failure returns an error turn and persists it to chat history without falling back to mock mode.
  3. Codebase inspection correctly queries the repository tree, matches candidate files (e.g. `Footer.tsx` for social links), and injects file content into the prompt context.
  4. Prompt for removing links does not propose creating route files or drafting ADRs.
  5. Mock mode correctly handles deletion prompts vs. new feature prompts according to archetype classification.

## Out of Scope

- Running full Modal sandboxes or in-sandbox browser agents during the grilling interview turn (grilling remains lightweight and serverless).
- Modifying the downstream Assembly Line Pipeline stages (Planner, Coder, Verifier, Reviewer).
- Adding full-text semantic vector indexing across target repositories (keyword matching against file paths and candidate components via GitHub API is sufficient).

## Further Notes

- Target application repositories created from the template already follow standard directory layouts (`app/routes/`, `app/components/`, `src/`), making path-based heuristic matching fast and reliable.
- This specification addresses the root cause of the absurd behavior reported by developers when modifying existing components in Factory Studio.
