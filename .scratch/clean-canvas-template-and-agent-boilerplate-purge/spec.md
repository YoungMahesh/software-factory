# Spec: Clean Canvas Invariant and Template Boilerplate Purge

Status: resolved
Triage: ready-for-agent

## Problem Statement

When a developer creates a new target application in Factory Studio (such as `counter-11` created from prompt "create a simple counter app with + and - buttons which will increment and decrement the number"), the generated application preserves the default template placeholder banner and copy:
"Application Workspace"
"Ready for development. Prompt Factory Studio to build features and components."
along with the framework header badge ("● TanStack Start").

The autonomous assembly line agents (Planner Agent and Coder Agent) mount the new application components (e.g. the counter widget) directly beneath or inside the existing placeholder container rather than replacing it. Additionally, the Reviewer Agent does not flag or reject pull requests that retain this placeholder copy. Consequently, end users receive generated web applications cluttered with development workspace chrome that is unrelated to their application domain requirements.

## Solution

Enforce the Clean Canvas Invariant end-to-end across the Software Factory and the Canonical Template Repository (`software-factory-09-test/tanstack-start-template`):

1. **Purge Placeholder Banner from Canonical Template Repository**:
   - Update `src/routes/index.tsx` in `software-factory-09-test/tanstack-start-template` to render an empty, clean main container canvas (`<main className="page-wrap px-4 py-8 min-h-screen"></main>`) devoid of "Application Workspace", guide copy, or promotional text.
   - Update `src/components/Header.tsx` brand badge default from "TanStack Start" to a neutral "App" placeholder.

2. **Defense-in-Depth Assembly Line Agent Instructions**:
   - **Planner Agent (`sandbox/factory/harness/prompts/planner_system.md`)**: Instruct the planner to inspect route components and header chrome for starter boilerplate (such as "Application Workspace", development hints, or generic template badges) and explicitly mandate in the implementation plan that they must be replaced by the target application's UI and synthesized title.
   - **Coder Agent (`sandbox/factory/harness/prompts/coder_system.md`)**: Instruct the coder to cleanly replace starter placeholder markup in `src/routes/index.tsx` and customize the header brand in `src/components/Header.tsx` to match the target application rather than appending components below placeholder cards.
   - **Reviewer Agent (`sandbox/factory/harness/prompts/reviewer_system.md`)**: Require `standardsCompliance` to check for and reject (`verdict: "rejected"`) pull requests where default template boilerplate copy (e.g., "Application Workspace", "Ready for development. Prompt Factory Studio to build features and components.", or stale template badges) is retained in application routes.

3. **Explicit Ticket Synthesis Acceptance Criteria**:
   - In `factory/ui/github/_issues.py` (`synthesize_ticket_content`), add explicit acceptance criteria for initial feature tickets requiring full replacement of default template placeholder elements in `src/routes/index.tsx` and updating the header brand title in `src/components/Header.tsx`.

4. **Domain Documentation & Architecture Record**:
   - Formalize the `Clean Canvas Invariant` in `CONTEXT.md`.
   - Record Architectural Decision Record `docs/adr/0062-clean-canvas-invariant-and-template-boilerplate-purge.md`.

## User Stories

1. As a developer prompting Factory Studio to build a counter application, I want the generated website to display only my counter interface without any leftover "Application Workspace" banners, so that the application looks completely custom and production-ready.
2. As a developer viewing a newly generated app in Live Preview, I want the top navigation header to display my application name instead of "TanStack Start", so that the brand accurately reflects my prompt.
3. As a developer cloning the canonical template before prompting, I want a clean, unobtrusive canvas, so that there is no demo marketing or placeholder clutter on screen.
4. As a Planner Agent inspecting an initial application repository, I want clear instructions to plan the replacement of template boilerplate in `src/routes/index.tsx` and `src/components/Header.tsx`, so that my plan explicitly directs the Coder Agent to build a clean UI.
5. As a Coder Agent executing an initial feature plan, I want clear guidance to overwrite starter placeholder cards rather than appending new components beneath them, so that the resulting git commit leaves a clean route hierarchy.
6. As a Reviewer Agent performing quality gate verification, I want an unambiguous standards compliance rule to fail pull requests containing template placeholder strings, so that regressions in canvas cleanliness never reach `main`.
7. As a developer reviewing a synthesized ticket in the Studio Issue Drawer, I want to see explicit acceptance criteria for replacing starter boilerplate and updating header branding, so that the work item scope is transparent.
8. As an operator running regression test suites, I want unit tests for ticket synthesis, agent prompt definitions, and reviewer checks to pass deterministically, so that future changes do not reintroduce boilerplate retention.

## Implementation Decisions

- **Canonical Template Repository Scope**:
  Update `software-factory-09-test/tanstack-start-template` directly via GitHub API commits on its `main` branch. `src/routes/index.tsx` becomes an empty styled `<main>` container; `src/components/Header.tsx` uses "App" as the neutral baseline.
- **Planner Prompt Instructions**:
  Add an explicit Clean Canvas Invariant section to `sandbox/factory/harness/prompts/planner_system.md` instructing the Planner to specify complete replacement of starter boilerplate in `src/routes/index.tsx` and custom naming in `src/components/Header.tsx`.
- **Coder Prompt Instructions**:
  Add clean-slate implementation rules to `sandbox/factory/harness/prompts/coder_system.md` forbidding appending new UI beneath placeholder cards and mandating header brand replacement.
- **Reviewer Prompt Instructions**:
  Add a blocker-level standards compliance rule to `sandbox/factory/harness/prompts/reviewer_system.md` that checks diffs for leftover template placeholder strings ("Application Workspace", "Ready for development", etc.).
- **Ticket Synthesis Criteria**:
  Update `synthesize_ticket_content` in `factory/ui/github/_issues.py` to inject acceptance criteria for initial tickets:
  `- [ ] Replace default starter template placeholder markup in src/routes/index.tsx with the new application UI.`
  `- [ ] Update the header brand in src/components/Header.tsx to display the application title.`
- **Domain Modeling**:
  Add `Clean Canvas Invariant` to `CONTEXT.md` and record ADR 0062 documenting the decision and trade-offs.

## Testing Decisions

- **What Makes a Good Test**:
  Tests must assert external observable behavior and contracts:
  1. `test_synthesize_ticket_content` asserts that generated tickets include the clean canvas and header brand replacement acceptance criteria.
  2. Subsystem prompt tests assert that the externalized prompts for Planner, Coder, and Reviewer contain the Clean Canvas Invariant requirements and reviewer rejection rules.
  3. Template verification asserts that `tanstack-start-template` builds cleanly with zero unreferenced imports or syntax errors.
- **Modules Tested**:
  - `factory/ui/github/_issues.py` evaluated via `tests/test_ui/test_synthesis.py`.
  - Externalized prompts evaluated via `tests/test_grill/` and harness tests.
- **Prior Art**:
  - `tests/test_ui/test_synthesis.py`: tests ticket generation structure and criteria.
  - `tests/test_ui/test_github_template.py`: tests template compatibility and repository instantiation.

## Out of Scope

- Rewriting git history of past test repositories (e.g. `counter-11`).
- Introducing multi-page navigation or changing the router architecture away from TanStack Start.
- Adding dynamic backend configuration services for header titles.

## Further Notes

- The canonical template repository is tracked at `software-factory-09-test/tanstack-start-template`.
- Credentials to push updates to GitHub are managed through ephemerally decrypted organization credentials (`get_test_org_token()`).
- ADR 0062 will be tracked under `docs/adr/0062-clean-canvas-invariant-and-template-boilerplate-purge.md`.
