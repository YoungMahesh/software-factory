# 0016. Hydration Affordance and Bundle Splitting

## Context
When loading the SSR dashboard, interactive buttons (`<button onClick={...}>`) rendered in the initial HTML were non-responsive until React client hydration completed. In large routes such as the project dashboard (containing SQL Scratchpad, Object Browser, and statically imported TanStack Devtools), the hydration gap was perceptible, causing false affordance where users attempted to click buttons before event handlers were attached.

## Decision
We decided to resolve this through visual hydration affordance and hydration minimization:
1. **Hydration State Gating**: Track client hydration via a `useHydrated()` hook. Render a subtle top-of-screen neon-green initialization bar that fades out once hydrated, and set `disabled={!isHydrated}` with `cursor-wait` and a connecting tooltip on interactive buttons during the pre-hydration window.
2. **Devtools Deferral**: Dynamically import TanStack Devtools in development mode only and exclude them from production builds, keeping the critical hydration bundle lean.
3. **Tab Code-Splitting**: Code-split heavy dashboard tabs (SQL Scratchpad and Object Browser) into lazy-loaded components with `<Suspense>`, allowing the core project overview and layout to hydrate near-instantaneously.

## Considered Options
- **Pre-Hydration Event Replay (Google jsaction pattern)**: Rejected due to added complexity of global DOM event queuing and synthetic event replaying across complex modal states.
- **Progressive Enhancement via URL Query Params**: Considered, but query-param driven modals add URL noise and do not solve non-navigation buttons (such as SQL execution, credential copying, or tab actions).
- **Client-Only Rendering (SPA Mode)**: Rejected because retaining SSR preserves Fast Contentful Paint and SEO/metadata capabilities.
