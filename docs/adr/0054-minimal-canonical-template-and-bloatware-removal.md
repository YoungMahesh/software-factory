# 0054: Minimal Canonical Template and Bloatware Removal

**Status**: Accepted

To provide a clean, unencumbered canvas for iterative AI application generation in Factory Studio, we decided to strip all demo marketing copy, secondary routes, promotional links, and devtools overlays from the Canonical Template Repository (`software-factory-09-test/tanstack-start-template`).

## Considered Options

- **Retain Full TanStack Starter Showcase**: Keeping the default marketing hero banner ("Start simple, ship quickly"), feature cards, `/about` route, footer branding, and TanStack social links. Rejected because developers and autonomous agents must waste conversational turns and prompt budget deleting demo bloatware rather than focusing on the target application's domain requirements.
- **Completely Blank Canvas (Empty Root Route with No Navbar)**: Removing all structure including header and theme toggle. Rejected because dark/light mode switching and a minimal navbar baseline provide high visual polish without encumbering the agent.
- **Minimal Application Shell with Brand Placeholder and Theme Toggle**: Purging all marketing text, demo cards, secondary routes, footer links, and devtools overlays, while preserving the clean container layout, design tokens, and ThemeToggle. Accepted.

## Consequences

- The Canonical Template Repository (`software-factory-09-test/tanstack-start-template`) contains only a single route (`src/routes/index.tsx`) and root layout (`src/routes/__root.tsx`).
- `src/routes/about.tsx` and `src/components/Footer.tsx` are permanently removed; `TanStackDevtools` is removed from the root layout.
- `src/components/Header.tsx` retains only the app brand placeholder and `ThemeToggle`.
- Newly generated applications in Factory Studio start on a clean, professional canvas ready for immediate feature synthesis.
- Target application scaffolding templates in `factory/ui/scaffold.py` reference `src/routes/` rather than the legacy `app/routes/`.
