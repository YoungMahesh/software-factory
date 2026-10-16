# Cohere Editorial Design System for Factory Studio and Testing Console

**Status**: Accepted

To eliminate generic dark-dashboard aesthetics and elevate Factory Studio and the Factory Testing Console to an enterprise AI standard, we decided to adopt the 2026 Cohere design system ([DESIGN.md](../../DESIGN.md)) across the entire frontend application.

Specifically:
1. **Hybrid Editorial Canvas**: The workspace shell, navigation, and conversational stream use a stark white canvas (`#ffffff`), soft stone secondary surfaces (`#eeece7`), and hairline containment dividers (`#d9d9dd`). Runtime execution modules (Live Preview container, Terminal Log Viewer, agent tool cards, and approval gates) are framed as dark `agent-console-card` blocks in deep near-black (`#17171c`) and deep enterprise green (`#003c33`).
2. **Typography Pairing**: Import Google Fonts (`Space Grotesk`, `Inter`, `JetBrains Mono`) to match Cohere's font split between monospaced-feeling display headlines (`Space Grotesk`), neutral high-legibility UI copy (`Inter`), and uppercase technical labels (`JetBrains Mono`).
3. **Pill-Centric Interactive Hierarchy**: Adopt 32px pill geometry for primary action buttons (`button-primary`), outlined pills (`button-pill-outline`) for filters and branch controls, coral (`#ff7759`) accent chips for taxonomy and question indicators, and underlined text links (`button-secondary`) for inline secondary actions.
4. **Tailwind v4 Token Integration**: Register design system tokens in `src/index.css` via `@theme` declarations and update atomic UI primitives (`Button`, `Badge`, `Input`, `Textarea`) to encapsulate Cohere design variants.
5. **Full System Scope**: Apply the design language across both Factory Studio (`StudioView`) and the Factory Testing Console (`TestingConsoleView`), modernizing configuration forms into soft-stone cards and telemetry into dark-feature bands while preserving existing state machines and data flows.

## Considered Options

- **Retaining Slate/Indigo Dark Theme**: Preserving the initial Tailwind dark dashboard theme. Rejected because it felt like a generic developer tool rather than a polished, state-of-the-art enterprise AI studio.
- **Pure Dark Inversion**: Inverting Cohere tokens into an exclusively dark command center. Rejected because the hybrid contrast between an airy editorial discussion canvas and high-contrast dark console execution blocks is the signature tension that makes Cohere's interface distinctive.
- **Factory Studio Isolation**: Modernizing only `StudioView` while leaving the top navigation and Testing Console in legacy styling. Rejected because visual dissonance between the global shell and child views degraded user trust.

## Consequences

- Registered `Cohere Editorial Design System` in `CONTEXT.md`.
- Updated `factory/ui/frontend/index.html` to load `Space Grotesk`, `Inter`, and `JetBrains Mono`.
- Updated `factory/ui/frontend/src/index.css` with `@theme` token definitions (`colors`, `radii`, `font families`).
- Refactored `Button`, `Badge`, `Input`, `Textarea` in `src/components/ui/` to support pill radii, near-black primaries, coral badges, and dark console variants.
- Decomposed and restyled `StudioView`, `StudioHeader`, `StudioChatPane`, `LivePreview`, `AppNavigation`, and `TestingConsoleView` within physical file line limits (<= 500 lines per ADR-0051).
