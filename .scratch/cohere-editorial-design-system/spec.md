# Spec: Cohere Editorial Design System for Factory Studio and Testing Console

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

Developers interacting with Factory Studio and the Factory Testing Console currently experience a generic dark-dashboard developer tool aesthetic dominated by muted slate-900 backgrounds, slate-800 borders, and default indigo accent buttons. This visual treatment creates several problems for developers:

1. **Monotonous Visual Hierarchy**: The uniform dark-slate canvas makes it difficult for developers to quickly distinguish high-level conversational intent and requirements grilling from technical execution details (such as tool invocations, plan approval gates, and streaming terminal logs).
2. **Generic Developer Tool Identity**: Rather than feeling like a state-of-the-art enterprise AI command workspace, the current interface feels like an unbranded open-source administrative dashboard, lacking typographic precision and editorial authority.
3. **Inconsistent Component Geometry**: Controls and badges across Factory Studio, the global navigation header, and the Testing Console use conventional 8px rounded rectangles without a cohesive spatial or interactive hierarchy between primary affirmative actions, secondary taxonomy filters, and destructive operations.
4. **Visual Dissonance Across Surfaces**: The live preview frame, prompt composer, activity drawer, and delivery gate cards share identical dark surfaces, creating visual monotony and failing to highlight the running application as the primary focal point of the studio.

## Solution

Modernize Factory Studio, the Factory Testing Console, and the shared global navigation shell by implementing the Cohere Editorial Design System (grounded in the project design specification and Architectural Decision Record 0053):

1. **Hybrid Editorial Canvas**:
   - Establish an airy, stark white editorial canvas and soft stone secondary surfaces with crisp hairline containment rules for the workspace shell, global navigation header, and chat history timeline.
   - Frame runtime execution modules—the Live Preview container, Terminal Log Viewer, agent tool cards, thinking accordions, and delivery gate cards—as dark console blocks rendered in deep near-black and deep enterprise green.
2. **Distinctive Typography Pairing**:
   - Integrate Google Fonts to replicate Cohere's signature split typography: tight display headlines for prominent titles and feature banners, neutral high-legibility sans-serif UI typography for default body copy and buttons, and monospace typography for technical badges, code blocks, and terminal streams.
3. **Pill-Centric Interactive Hierarchy**:
   - Standardize all primary call-to-action buttons on 32px pill geometry rendered in near-black with white text (or high-contrast white on dark console surfaces).
   - Standardize secondary controls, repository branch pickers, and viewport toggles on outlined pill geometry with transparent backgrounds and hairline borders.
   - Introduce coral accent chips for question indicators and taxonomy markers, and clean underlined text links for inline secondary actions.
4. **Tailwind Design System Tokens & Atomic Primitives**:
   - Register custom design system tokens (colors, border radii, typography) in the global stylesheet.
   - Refactor atomic UI primitives (buttons, badges, text inputs, textareas) into reusable components adhering to the design system tokens.
5. **Full System Scope**:
   - Apply the design language across both Factory Studio and the Factory Testing Console, modernizing parameter configuration forms into soft-stone cards and real-time execution telemetry into dark feature bands while preserving existing data flows, telemetry streaming, and state machines.
6. **Physical File Line Budget Adherence**:
   - Decompose newly styled component markup into modular internal helpers to strictly maintain the 500-line physical budget across all modified production files.

## User Stories

1. As a developer opening Factory Studio, I want to see an airy white and soft stone editorial canvas, so that the workspace feels calm, focused, and executive.
2. As a developer reading conversational prompts in Factory Studio, I want my submitted messages rendered in soft stone cards with ink text, so that my input is distinct from assistant responses.
3. As a developer participating in requirement grilling, I want Grilling Assistant question frontiers rendered in crisp white cards with hairline borders and coral question markers, so that interview questions are immediately scannable.
4. As a developer reviewing a synthesized implementation plan, I want the approval card styled as a dark console card with a near-black background and white text, so that execution gates stand out with high contrast.
5. As a developer dispatching a plan, I want the "Approve Plan & Dispatch" button styled as a prominent 32px pill button, so that the primary action has a clear, satisfying click target.
6. As a developer watching agent stages execute, I want tool chips and command cards rendered as dark console blocks, so that machine execution feels distinct from human dialogue.
7. As a developer observing reasoning steps, I want the thinking accordion rendered in deep near-black with glowing status dots, so that background LLM reasoning is clearly grouped.
8. As a developer reviewing resolved feature pull requests, I want the Delivery Gate Card rendered as a structured console card with clear test verdicts and squash-merge controls, so that shipping code feels authoritative.
9. As a developer viewing a running web application, I want the Live Preview framed inside a rounded 22px card with a dark console toolbar, so that the target application feels like a featured product mockup.
10. As a developer switching git branches in Live Preview, I want the branch selector styled as an outlined pill button with monospaced text, so that branch controls are recognizable and compact.
11. As a developer whose preview server is stopped or provisioning, I want to see a soft stone or pale green wash empty state with thin-line geometric status diagrams, so that container state transitions are visually clear.
12. As a developer composing a prompt in Factory Studio, I want the Prompt Composer enclosed in a soft-stone panel with a crisp white input box and near-black pill submit button, so that prompt drafting feels inviting and distraction-free.
13. As a developer toggling requirement grilling mode, I want the grill toggle styled with crisp typography and subtle pill styling, so that I can easily switch between direct dispatch and interview modes.
14. As a developer rolling back a conversational turn, I want destructive rollback actions styled with coral accents or clean text links rather than jarring red boxes, so that dangerous actions are evident without visual alarm.
15. As a developer navigating between Factory Studio and the Factory Testing Console, I want the global navigation bar styled with a white background, hairline bottom border, and pill tab switchers, so that the top-level shell feels unified.
16. As a developer configuring test parameters in the Factory Testing Console, I want repository and issue configuration panels styled as soft stone cards with hairline borders, so that dense forms remain readable.
17. As a developer monitoring live pipeline execution in the Factory Testing Console, I want the stage stepper and terminal output rendered inside a deep enterprise green or near-black feature band, so that real-time execution logs maintain high visual contrast.
18. As a developer reviewing terminal logs in either view, I want the Terminal Log Viewer styled with dark console backgrounds and monospaced font rendering, so that ansi outputs and stack traces remain perfectly legible.
19. As a developer opening slide-over panels (Issue Drawer and Activity Drawer), I want drawers styled with soft stone surfaces, hairline dividers, and coral status badges, so that secondary panels seamlessly match the workspace.
20. As a developer typing in input fields and textareas, I want focused inputs to display a subtle violet focus ring, so that keyboard focus is distinct and accessible.
21. As a developer inspecting badges across the app, I want status badges to use semantic variants (coral for taxonomy, pale green for success, dark console for active stages), so that status meaning is intuitive.
22. As an engineer maintaining the codebase, I want all production files to remain under 500 physical lines, so that the code remains modular and compliant with repo line budgets.

## Implementation Decisions

- **Global Design Tokens**: Register custom tokens in the global CSS file (`colors` including canvas white, soft stone, near-black, deep green, coral, pale green, pale blue, hairline, and ink; `radii` including 22px media card and 32px pill; `fonts` for display, sans, and mono).
- **Typography Integration**: Load Google Fonts (`Space Grotesk`, `Inter`, `JetBrains Mono`) with `font-display: swap` in the HTML document shell, applying display typography to headings and sans-serif typography to UI copy and buttons.
- **Atomic Primitives Refactoring**:
  - Update Button component to support `primary` (32px pill in near-black or inverted white on dark), `pill-outline` (transparent pill with hairline border), `secondary` (clean underlined text), and `danger` (coral outline/text).
  - Update Badge component to support `coral` taxonomy chips, `console` dark status chips, `success` pale-green chips, and `stage` monospaced chips.
  - Update Input and Textarea components to use crisp white backgrounds, hairline borders, and violet focus indicators.
- **Global Header Modernization**: Update the navigation header component to a stark white background with hairline bottom divider, dark logo badge, and pill navigation tabs.
- **Factory Studio Header & Chat Stream Modernization**:
  - Update Studio header to a soft stone surface with pill action buttons, monospaced branch selector pill, and coral issue counter.
  - Style user chat messages as soft stone cards with ink text.
  - Style Grilling Assistant interview frontiers as white cards with hairline borders, Space Grotesk question titles, and coral question badges.
  - Style Plan Approval, Tool Invocations, and Delivery Gate cards as dark console blocks with near-black backgrounds, muted text, and monospaced metadata.
- **Prompt Composer Modernization**: Update prompt composer container to a soft stone panel with white textarea, hairline containment, and near-black pill send button.
- **Live Preview Container Modernization**: Wrap the live preview frame in a 22px radius card with a hairline border, near-black console toolbar, monospaced branch selector pill, and soft-stone/pale-green empty state.
- **Factory Testing Console Modernization**: Update configuration panels to soft stone cards with hairline borders, and update stage stepper, telemetry logs, and terminal viewer into a deep enterprise green / near-black feature band.
- **Physical Line Limit Management**: Extract any auxiliary card rendering logic or subcomponents into dedicated internal module files to ensure no file exceeds 500 physical lines.

## Testing Decisions

- **Test Seam (Highest Possible Seam)**: The feature will be tested via the existing **Frontend Component and Integration Test Suite** using Vitest and `@testing-library/react`.
- **Behavioral Assertions**: Tests will verify external user-visible behavior:
  - Primitive components render with correct pill geometry, variant classes, and accessible attributes.
  - Factory Studio renders message streams (user messages, grilling frontiers, dark console cards) and handles prompt submissions, plan approvals, and branch switches.
  - Factory Testing Console renders configuration panels and execution steppers without breaking parameter dispatches or telemetry streaming.
  - Live Preview renders the 22px container frame and toolbar controls.
  - The production build (`pnpm build`) succeeds without TypeScript compilation errors.
- **Prior Art**:
  - `src/components/ui/Primitives.test.tsx` (tests atomic button, badge, input primitives).
  - `src/views/StudioView.test.tsx` and `src/App.test.tsx` (tests end-to-end studio rendering, chat interactions, and preview flows).
  - `src/views/TestingConsoleView.test.tsx` (tests testing console layout and telemetry integration).
  - `src/components/LivePreview.test.tsx` (tests preview frame and toolbar).

## Out of Scope

- Backend API modifications, database schema adjustments, or Modal sandbox spawner logic (this is strictly a frontend design system implementation).
- Replacing client-side business logic, state machines, React Query hooks, or SSE telemetry pipelines.
- Modifying proprietary font licensing or distributing proprietary font files (system relies on open-source Google Font fallbacks: Space Grotesk, Inter, JetBrains Mono).
- Modifying the headless CLI interface (`factory/run.py`).

## Further Notes

- Architectural context and design tokens are documented in [docs/adr/0053-cohere-editorial-design-system-for-factory-studio.md](../../docs/adr/0053-cohere-editorial-design-system-for-factory-studio.md) and [DESIGN.md](../../DESIGN.md).
- Domain glossary definitions are tracked in [CONTEXT.md](../../CONTEXT.md).
