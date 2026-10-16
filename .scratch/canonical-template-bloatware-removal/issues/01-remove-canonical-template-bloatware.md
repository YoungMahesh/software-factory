# 01: Remove Bloatware from Canonical Template Repository

**What to build:**
Streamline the Canonical Template Repository (`software-factory-09-test/tanstack-start-template`) into a minimal, unencumbered application starter for Factory Studio:
- **Root Route Clean-up (`src/routes/index.tsx`)**: Remove promotional marketing copy, the "Start simple, ship quickly" hero banner, "TANSTACK START BASE TEMPLATE" kicker, external router guide link, 4 marketing feature cards ("Type-Safe Routing", "Server Functions", etc.), and quick-start instructions. Replace with a clean, neutral "Application Workspace" container with a subtle guidance prompt ("Ready for development. Prompt Factory Studio to build features and components.").
- **Navigation Header Streamlining (`src/components/Header.tsx`)**: Retain a minimal top navigation bar with the application brand placeholder and `ThemeToggle`. Purge all external links (TanStack Docs, X/Twitter, GitHub) and the `/about` route link.
- **Delete Secondary Routes & Footer**: Permanently delete `src/routes/about.tsx` (establishing a single-route `/` baseline) and `src/components/Footer.tsx`.
- **Root Layout Update (`src/routes/__root.tsx`)**: Remove imports and rendering of `Footer` and `TanStackDevtools` to keep the live preview canvas unobstructed.
- **Route Tree Synchronization (`src/routeTree.gen.ts`)**: Regenerate and update the route tree export to drop `/about` and only export the root and index routes.
- **Build and Test Verification**: Validate in a temporary scratch clone with `pnpm test` and `vite build` (`pnpm run build`) to ensure zero broken imports, syntax errors, or bundling issues.
- **Deploy to Canonical Template**: Push the verified commit to `main` on `software-factory-09-test/tanstack-start-template` using decrypted organization credentials.
- **Scaffolding Invariant Verification**: Confirm that `python3 -m unittest -k scaffold tests/test_ui.py` passes cleanly against the updated template and scaffolding definitions.

**Blocked by:** None (can start immediately)

**Status:** resolved
**Triage:** resolved

- [x] Clone `software-factory-09-test/tanstack-start-template` into a temporary scratch directory using organization credentials.
- [x] Replace `src/routes/index.tsx` marketing hero and cards with a clean, tasteful application workspace canvas.
- [x] Streamline `src/components/Header.tsx` to retain only the brand placeholder and `ThemeToggle`, removing all external and demo links.
- [x] Delete `src/routes/about.tsx`.
- [x] Delete `src/components/Footer.tsx`.
- [x] Update `src/routes/__root.tsx` to remove `Footer` and `TanStackDevtools` imports and elements.
- [x] Regenerate `src/routeTree.gen.ts` without `/about`.
- [x] Execute `pnpm test` and `pnpm run build` in the temporary clone to assert zero compilation, type, or test failures.
- [x] Commit and push changes to `main` on `software-factory-09-test/tanstack-start-template`.
- [x] Run `python3 -m unittest -k scaffold tests/test_ui.py` to verify scaffolding invariants pass.
