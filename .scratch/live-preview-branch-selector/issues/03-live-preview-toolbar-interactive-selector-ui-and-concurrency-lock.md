# 03: Live Preview Toolbar Interactive Selector UI and Concurrency Lock

**What to build:**
Upgrade the active branch badge in the Live Preview toolbar into an interactive dropdown selector with strict concurrency locking during active agent assembly line jobs. Developers can click the branch pill to inspect all candidate branches for the repository, select a branch to switch the live preview in place, observe real-time switching feedback with a loading spinner, and enjoy automatic preview refreshes. When an Assembly Line Pipeline job is active (`RUNNING` or `QUEUED`), the branch selector is strictly disabled with a lock icon and tooltip to prevent concurrent git conflicts while agents are generating code.

**Blocked by:** 02: In-Container In-Place Git Switching and Diff-Aware Dependency Resolution

**Status:** ready-for-agent

- [ ] `#preview-branch-badge` in `LivePreview.tsx` is transformed into an interactive dropdown menu with `GitBranch` icon, branch label, and `ChevronDown`.
- [ ] Dropdown lists available branches with a checkmark indicator next to the currently active branch.
- [ ] Selecting a branch invokes branch switching, displays a loading spinner inside the badge, and disables interaction during the transition.
- [ ] Concurrency guard: Selector is strictly disabled with a lock icon and explanatory tooltip when an Assembly Line Pipeline job is `RUNNING` or `QUEUED`.
- [ ] `StudioView.tsx` integrates TanStack Query to fetch branches for the active repository, invalidating cache on repository switch, job completion, and drawer interactions.
- [ ] Switching branch triggers automatic preview iframe refresh upon completion.
- [ ] Dropdown supports keyboard navigation and click-away closing.
- [ ] Automated Vitest component and integration tests verify dropdown rendering, branch selection, loading states, concurrency locking, and query invalidation.
