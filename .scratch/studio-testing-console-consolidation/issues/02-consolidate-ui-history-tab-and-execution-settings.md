# 02: Consolidate UI into Factory Studio with History Tab and Execution Settings

**What to build:** Retire the Factory Testing Console view and navigation tab switcher, redirect `/console` paths to `/` with query parameters preserved, expand the Activity Drawer with a third History tab for inspecting past runs, enhance the Studio Issue Drawer with collapsible execution settings (model selection, VM sandbox virtualization) wired to instant dispatch, and delete dead console components.

**Blocked by:** 01: Canonicalize Backend API Routes and Frontend Client

**Status:** done

- [x] Top navigation switcher tab in `AppNavigation.tsx` is removed; navigation header renders only product branding, active job status indicator, and current repository badge.
- [x] Direct navigation to `/console` in `App.tsx` redirects seamlessly to `/` while preserving URL search parameters (such as `?repo=...`).
- [x] Slide-over `ActivityDrawer.tsx` is expanded from two tabs (`Timeline`, `Logs`) to three tabs: `Timeline`, `Logs`, and `History`.
- [x] The `History` tab in `ActivityDrawer.tsx` renders a multi-run table showing Job ID, repository, feature name, status badge, stage, and relative timestamp, with controls to inspect logs in place and cancel running jobs.
- [x] Studio Issue Drawer (`IssueDrawer.tsx`) includes a collapsible "Execution Settings" panel supporting Model selection (DeepSeek V4.1 Flash vs MiMo-V2.6-Flash) and VM Sandbox virtualization toggles.
- [x] Instant dispatch and milestone batch dispatch in `IssueDrawer.tsx` pass configured execution settings (`model`, `vm`) in their dispatch payload.
- [x] Obsolete view and form components (`TestingConsoleView.tsx`, `JobConfigPanel.tsx`, `TestingConsoleView.test.tsx`) are deleted.
- [x] Frontend integration tests in `App.navigation.test.tsx`, `App.routing.test.tsx`, `ActivityDrawer.test.tsx`, and `IssueDrawer.test.tsx` pass cleanly, asserting the unified Studio workspace and testing seam interactions.
