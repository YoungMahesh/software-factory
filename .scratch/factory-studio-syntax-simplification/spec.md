# Spec: Factory Studio Code Syntax Simplification and Boilerplate Reduction

Status: resolved

## Problem Statement

Engineers and autonomous coding agents maintaining Factory Studio face substantial syntactic boilerplate, repetitive state-tracking code, and high cognitive overhead across both the frontend React single-page application and the supporting web service.

Specifically:
1. The primary studio workspace component accepts over 20 discrete props, requiring extensive parameter forwarding, cluttered container components, and bloated mock configurations across test suites.
2. Asynchronous operations (repository creation, preview provisioning, job dispatching, and prompt submission) rely on over 10 manual state variables tracking pending and error statuses alongside imperative lifecycle hooks, rather than taking advantage of declarative data-fetching primitives already present in the workspace dependencies.
3. Long utility class strings exceeding 80 characters are duplicated across dozens of interactive elements, obscuring document structure and visual hierarchy.
4. Large modal dialogues and disconnected state overlays are inlined directly within the main split-pane layout component, swelling the container beyond 600 lines and tangling layout concerns with modal form state.
5. Telemetry event stream aggregation into conversational chat turns is implemented imperatively inside the top-level application component, making event-folding logic difficult to test in isolation.
6. Loose type definitions with optional fields for preview runtime state force repetitive optional chaining and defensive fallback checks across multiple views.
7. Web API route handlers repeat manual error-handling blocks and duplicate endpoint registrations.

This verbosity increases token consumption during agent workflows, slows down developer comprehension, and elevates the likelihood of accidental regressions when adding new studio features.

## Solution

Streamline the Factory Studio implementation by reducing boilerplate, deduplicating syntax, and adopting declarative patterns across the frontend application and backend API, while maintaining 100% functional parity, preserving existing user interfaces and styling, and maintaining passing test suites:

1. **Declarative Server State Management**: Adopt mutation and query hooks for asynchronous backend interactions (repository lists, repository creation, preview lifecycle management, and prompt execution), eliminating manual loading/error flags and imperative request waterfalls.
2. **Consolidated Studio Context**: Replace extensive prop drilling with a unified studio context and hook that provides access to preview state, active job telemetry, and user actions.
3. **Micro-UI Primitives**: Introduce lightweight, styled UI primitives for buttons, icon triggers, badges, and form inputs that encapsulate common style classes and states (loading spinners, disabled styles) through concise variant properties.
4. **Modal Component Decoupling**: Extract inline overlays—specifically the repository creation dialog and the environment disconnection banner—into standalone, focused components with encapsulated form state.
5. **Pure Telemetry Event Folding**: Extract the logic that maps incoming telemetry events to conversation turns into a pure reducer function, removing imperative state mutations from the top-level shell.
6. **Discriminated Union Runtime States**: Refactor runtime state definitions for the preview environment into strict discriminated unions to replace defensive null checks with exhaustive type narrowing.
7. **Consolidated API Handlers**: Leverage global exception mapping and unified route definitions in the backend web service to eliminate repetitive error transformations and duplicate route declarations.

## User Stories

1. As a developer browsing Factory Studio, I want the web interface to behave identically in responsiveness, layout, and visual appearance, so that my development workflow is completely undisturbed.
2. As a developer creating a new application in Factory Studio, I want the repository creation modal to handle submission, loading spinners, and validation errors seamlessly, so that project creation remains smooth and responsive.
3. As a developer submitting conversational prompts to the assembly line, I want prompt inputs to lock during active turns and unlock upon completion, so that I cannot submit conflicting requests.
4. As a developer observing an active agent turn, I want streaming thought disclosures, tool step chips, and execution status badges to update in real time without lag or dropped updates, so that I have full visibility into what the agent is doing.
5. As a developer testing responsive layouts, I want live preview device viewport toggles (desktop, tablet, mobile) to resize the preview frame immediately, so that I can inspect mobile and desktop views effortlessly.
6. As a developer interacting with the preview environment, I want manual reload triggers and automated event-driven iframe refreshes to work reliably, so that the latest code changes are always displayed.
7. As a developer whose preview sandbox encounters an idle timeout or stopped state, I want to see an explicit disconnection dialog with preserved chat history and a single-click reconnect action, so that I can resume work without losing context.
8. As a developer switching between Studio View and Console View, I want view transitions to remain instant and retain active job telemetry, so that I can inspect raw terminal logs whenever necessary.
9. As an engineer writing component tests for Studio View, I want to instantiate test scenarios with concise helpers rather than passing 20+ mock callbacks, so that tests are faster to author and easier to maintain.
10. As an autonomous coding agent implementing new studio features, I want concise component files with clear boundaries, so that I can read, modify, and verify code within small token budgets.
11. As an autonomous coding agent, I want typed discriminated unions for sandbox preview states, so that compiler errors immediately highlight unhandled lifecycle transitions.
12. As a frontend maintainer, I want button and input styling encapsulated in reusable primitives, so that updating accent colors or focus rings only requires modifying a single definition.
13. As a frontend maintainer, I want modal form states isolated within their respective components, so that modifying modal fields cannot cause unintended re-renders of the live preview or chat timeline.
14. As a frontend maintainer, I want chat turn aggregation from streaming telemetry to run through a pure reducer function, so that complex streaming edge cases can be verified through unit tests without mounting React trees.
15. As a backend maintainer, I want domain exceptions like repository creation errors automatically mapped to appropriate HTTP status codes, so that endpoints do not repeat identical try/except blocks.
16. As a backend maintainer, I want unified route definitions for studio endpoints, so that route aliases do not require duplicating function bodies.
17. As a QA engineer running the test suite, I want all existing component, integration, and backend tests to pass without regression, so that code simplification introduces zero functional defects.

## Implementation Decisions

- **State Management Migration to TanStack Query**:
  Transition all data-fetching operations (fetching repository lists, scratch metadata, milestone lists, active preview status) and data-modifying operations (creating repositories, launching previews, stopping previews, submitting prompt turns) to query and mutation hooks provided by the query client library already present in the workspace. Automatically derive pending states, error messages, and cache invalidations from query and mutation descriptors rather than managing individual boolean state flags.

- **Studio Context & Action Dispatch Seam**:
  Establish a unified context and consumer hook for Factory Studio state. The context will expose the selected repository, active preview environment state, in-flight execution flags, active job telemetry, and action handlers (launch preview, stop preview, reconnect environment, send prompt, open drawer). The main studio workspace component will consume this context directly, reducing its public interface to minimal layout props.

- **Composable UI Primitives**:
  Create lightweight component primitives encapsulating the repository's Tailwind styling patterns:
  - Button primitive supporting variants (primary, secondary, danger, ghost), sizes (sm, md), loading state with automated spinner icon rendering, and disabled handling.
  - Form input and textarea primitives with standardized border, background, and focus ring tokens.
  - Status badge primitive supporting stage indicators and status pills.

- **Modal Component Separation**:
  Decompose the monolithic studio layout component into focused presentation units:
  - A dedicated repository creation dialog component containing name and description inputs, client-side validation, submission handling, and error alerting.
  - A dedicated disconnection alert dialog component presenting idle timeout explanations, active branch indicators, dismiss controls, and reconnect triggers.
  - A prompt composer subcomponent encapsulating input locking, keyboard shortcuts (Enter to send, Shift+Enter for newline), in-flight status indicators, and submission triggers.

- **Pure Reducer for Agent Event Stream Folding**:
  Extract the stream event folding algorithm that processes telemetry events into conversational chat turns into a pure, standalone function. The function will take the existing list of chat messages and a collection of telemetry events, returning an updated immutable list of chat messages with updated reasoning text and deduplicated tool execution chips.

- **Preview State Type Shape (Prototype Reference)**:
  Replace the loose optional interface for preview state with a strict discriminated union encoding valid lifecycle stages:
  ```ts
  type PreviewState =
    | { status: "IDLE"; branch: null; preview_url: null; logs: string[]; error_message: null }
    | { status: "PROVISIONING"; stage: PreviewStage; branch: string; preview_url: null; logs: string[]; error_message: null }
    | { status: "SERVING"; preview_url: string; branch: string; logs: string[]; error_message: null }
    | { status: "STOPPED"; branch: string; preview_url: null; logs: string[]; error_message: null }
    | { status: "FAILED"; branch: string | null; preview_url: null; logs: string[]; error_message: string };
  ```

- **Backend Exception Mapping and Handler Simplification**:
  Configure FastAPI custom exception handlers for domain-specific errors (such as repository creation failures). Remove repetitive try/except blocks from endpoint functions, allowing unhandled domain exceptions to be automatically converted to structured JSON responses with appropriate HTTP status codes. Consolidate aliased route paths using multiple route decorators on shared handlers.

## Testing Decisions

- **Testing Philosophy**:
  Tests must verify external behavioral contracts, user-facing interactions, and network boundary conditions rather than internal component syntax or implementation mechanics. Refactoring syntax, extracting components, or migrating state management must not require rewriting behavioral assertions.

- **Frontend Component & Integration Seam (`factory/ui/frontend/src/`)**:
  - The highest frontend seam is the existing component and view test suites executed with Vitest and React Testing Library:
    - View tests exercising repository selection, prompt submission, input locking, in-flight progress feedback, preview status badges, manual refresh button triggers, and disconnect/reconnect workflows.
    - Application shell tests exercising tab navigation between Studio View and Testing Console View, SSE stream event rehydration, and drawer open/close behavior.
    - Component tests for Live Preview verifying device viewport sizing, reload button callbacks, and terminal log expansion.
  - Add isolated unit tests for the newly extracted pure telemetry event folding reducer function to ensure comprehensive coverage of reasoning deltas and tool chip deduplication across multiple agent stages.

- **Backend Web Service Seam (`tests/test_ui.py`)**:
  - The highest backend seam is the existing FastAPI TestClient suite:
    - HTTP requests asserting response status codes, payload structures, and error details for repository listings, repository creation, prompt submission, and preview lifecycle endpoints.
    - Regression assertions verifying that route aliases (such as `/api/repos` and `/api/studio/repos`) return identical responses.
    - Verification that domain exceptions continue to produce expected 4xx and 5xx JSON error responses with detailed messages.

- **Prior Art**:
  - Existing frontend test suites: `StudioView.test.tsx`, `App.test.tsx`, `LivePreview.test.tsx`, and `useJobStream.test.ts`.
  - Existing backend test suites: `tests/test_ui.py` and `tests/test_ui_events.py`.

## Out of Scope

- Changing the visual design system, color palette, typography, or component aesthetics of Factory Studio.
- Changing the public HTTP REST endpoint signatures or the Server-Sent Events (SSE) telemetry wire protocol.
- Modifying the underlying Modal sandbox orchestration, in-sandbox assembly line pipeline execution, or dev server supervision scripts.
- Rewriting the backend web service in TypeScript/Node.js; the backend remains a single-process Python FastAPI application.
- Altering the git commit accumulation model or GitHub issue tracking conventions in target test repositories.

## Further Notes

- Governed by ADR 0036 (Compiled Vite SPA for Factory Studio) and ADR 0038 (Unified Studio Sandbox for Live Preview and In-Sandbox Agent Execution).
- Adheres strictly to the domain glossary in `CONTEXT.md`: uses canonical terms Unified Studio Sandbox, Factory Studio, Modal Application Tunnel, Agent Event Stream, and Assembly Line Pipeline.
