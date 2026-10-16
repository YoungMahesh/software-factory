# Spec: Minimal Canonical Template and Bloatware Removal

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

When a developer in Factory Studio creates a new target application, the newly generated repository inherits the full default showcase from the canonical starter template. This template currently includes substantial demo bloatware:
1. A promotional hero banner on the index route featuring "TANSTACK START BASE TEMPLATE", the headline "Start simple, ship quickly", and introductory starter paragraphs.
2. Multiple marketing feature cards promoting framework capabilities ("Type-Safe Routing", "Server Functions", "Streaming by Default", "Tailwind Native") and a "Quick Start" guide instructing users to edit source files.
3. Promotional external links in the top header and footer leading to external documentation and social media accounts (TanStack Docs, X/Twitter, and GitHub).
4. A secondary demo route (`/about`) with demo marketing copy that adds unnecessary routing complexity to newly initialized single-page applications.
5. A floating router developer tools overlay in the preview window that obscures bottom-right application controls.

Because of this bloatware, developers and autonomous coding agents in Factory Studio are forced to waste prompt budget, conversational turns, and sandbox build cycles deleting showcase markup, extra routes, and external links before they can begin implementing the actual application domain logic.

## Solution

Transform the Canonical Template Repository into a minimal, production-grade application shell that provides an immediate, unencumbered canvas for application development:

1. **Purge Promotional Content from Home Route**:
   - Replace the hero banner, marketing feature cards, external documentation buttons, and quick-start instructions on the root route with a clean, neutral application container ("Application Workspace" and a subtle development guidance message).
   - Retain full Tailwind design system styling and color variables so newly generated components blend into a polished container immediately.

2. **Streamline Top Navigation Header**:
   - Retain a minimal application header featuring an application title placeholder and the interactive theme toggle.
   - Remove all external social links, documentation links, and demo route links.

3. **Eliminate Secondary Routes and Footer**:
   - Remove the secondary `/about` route and delete its component, keeping the initial application strictly single-route.
   - Delete the footer component and its external attribution links from the root application layout.
   - Remove the router developer tools panel from the root layout to maintain an unobscured live preview window.

4. **Regenerate Route Tree and Ensure Build Integrity**:
   - Update the generated route tree to cleanly drop the removed route without compilation errors or dangling imports.
   - Verify that the template build and test suites pass with zero warnings or errors.

5. **Align Scaffolding Service and Domain Architecture**:
   - Update repository scaffolding templates to reference the canonical source routing directory rather than legacy routing conventions.
   - Formalize the Canonical Template Repository in the domain glossary and document the design in Architectural Decision Record 0054.

## User Stories

1. As a developer creating a new application in Factory Studio, I want the home page to be free of framework promotional copy, so that I can see my application workspace immediately.
2. As a developer viewing a newly provisioned app in Live Preview, I want a clean, polished container with neutral styling, so that the canvas feels ready for my custom features.
3. As a developer interacting with the initial app in Live Preview, I want the theme toggle to continue functioning smoothly between light and dark modes, so that dark-mode styling is preserved.
4. As a developer navigating the initial application header, I want to see only my application title and theme toggle, so that my navigation is not cluttered with external framework links or social media icons.
5. As an autonomous coding agent given a feature request, I want the initial route tree to contain only a single root route, so that I do not need to spend planning cycles removing unwanted demo routes.
6. As an autonomous coding agent modifying the home view, I want clean, concise starter markup, so that I do not have to parse or delete lengthy marketing feature grids.
7. As a developer evaluating an application in Live Preview, I want the bottom-right corner to be unobstructed by floating devtools overlays, so that buttons and interactive widgets in that area are clickable.
8. As a developer instantiating a target repository, I want the template repository to compile cleanly without broken imports or missing route files, so that my first dev server launch succeeds immediately.
9. As an autonomous coding agent inspecting repository domain documentation, I want `CONTEXT.md` to define the Canonical Template Repository clearly, so that I understand where baseline application files originate.
10. As an autonomous coding agent reading `docs/adr/`, I want baseline architecture records to accurately reflect the source route directory, so that my planned route additions follow canonical conventions.
11. As a developer reviewing feature pull requests, I want the git diff of newly initialized applications to remain minimal, so that initial review focuses purely on my requested feature.
12. As an operator running repository scaffolding scripts, I want new repositories generated from the canonical template to pass all automated pre-flight guards without manual adjustments.
13. As a test suite running against the canonical template repository, I want automated unit and build tests to pass with an exit code of zero, so that template regression testing is deterministic.
14. As an assembly line reviewer agent auditing a feature implementation, I want no unreferenced template files or dead route imports to trigger compliance warnings.
15. As a developer using Factory Studio on mobile or narrow viewports, I want the clean header and home canvas to be fully responsive without horizontal overflow caused by wide marketing cards.

## Implementation Decisions

- **Canonical Template Repository Scope**:
  Modifications are applied directly to the canonical template repository on its default branch. Existing target repositories previously cloned from the template are untouched, while all subsequent repository generation calls will inherit the streamlined baseline.

- **Root Route Presentation**:
  The root route component will render a responsive container containing a clean application workspace shell with an unobtrusive heading and development hint. All hardcoded TanStack marketing copy, feature comparison grids, and quick-start instructions are purged.

- **Navigation Header Component**:
  The navigation header component is retained in the root application layout but stripped of external anchor elements (social media icons and external documentation links) and secondary route links. It retains the application title brand link and the theme toggle component.

- **Removal of Secondary Routes and Layout Footers**:
  The secondary route file is deleted from the route directory. The footer component is removed from the component hierarchy, and the root layout shell is updated to omit both the footer and the router developer tools panel.

- **Route Tree Synchronization**:
  The auto-generated route tree specification is updated to reflect the single-route hierarchy. Type definitions and route tree exports must only export the root route and index route.

- **Scaffolding and Domain Alignment**:
  Target repository scaffolding services are updated to reference the standard source route directory in baseline architectural decision records and domain documentation templates. The canonical template repository is added to the system domain glossary.

## Testing Decisions

- **What Makes a Good Test**:
  Good tests assert observable external behavior and build invariants rather than internal AST structure. Tests must verify that:
  1. The canonical template builds successfully into production client and server bundles without syntax or type errors.
  2. The canonical template test runner executes and passes all test suites.
  3. The route tree compiles cleanly and contains no references to removed routes.
  4. Repository scaffolding in the software factory produces valid, complete repositories satisfying all pre-flight guards.

- **Modules and Repositories Tested**:
  - The canonical template repository: evaluated at the build bundle seam (`pnpm run build`) and test execution seam (`pnpm test`).
  - Target repository scaffolding service: evaluated at the unit test seam asserting accurate route directory conventions and scaffolding file generation.

- **Prior Art**:
  - `tests/test_ui.py`: exercises template instantiation, repository scaffolding, and pre-flight validation.
  - Template repository test harness: node test runner configuration executing automated verification in the target project.

## Out of Scope

- Retroactively modifying or rewriting the git history of existing target repositories already deployed in the test organization.
- Altering the core runtime dependencies (TanStack Start, React 19, Tailwind CSS v4, Vite) or replacing the underlying routing engine.
- Introducing complex starter features (such as authentication providers, persistent databases, or backend microservices) into the template.
- Modifying Factory Studio's UI components outside of target template instantiation and scaffolding references.

## Further Notes

- The canonical template repository is tracked at `software-factory-09-test/tanstack-start-template`.
- Credentials to access and update the repository on GitHub are managed through ephemerally decrypted organization credentials.
- Architectural Decision Record 0054 documents the accepted trade-off between starter demonstration showcase and unencumbered AI-ready application canvas.
