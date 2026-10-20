# 02: Pre-Merge Diff Viewer with Dual Scope and Side-by-Side Toggle

**What to build:**
An interactive Git comparison surface in the right canvas under the "Git Diff" view mode. Developers can review multi-file changes across the repository before triggering the In-Studio Merge Control. The viewer features a dual-scope selector allowing developers to toggle between "Working Tree Changes" (uncommitted edits inside the live sandbox) and "Branch Changes" (accumulated feature branch commits against the main trunk). The view renders a summary banner with addition/deletion statistics, expandable file diff cards, and a layout toggle switching between Unified hunk diffs and Split two-column side-by-side diffs with synchronized scrolling.

**Blocked by:** 01 (In-Studio File Explorer & Code Viewer with Canvas View Switcher)

**Status:** ready-for-agent

- [ ] Selecting "Git Diff" in the canvas header renders the Pre-Merge Diff Viewer.
- [ ] A scope selector allows toggling between "Working Tree Changes" (container uncommitted modifications) and "Branch Changes" (feature branch compared to main trunk).
- [ ] A summary header displays total additions, total deletions, and count of modified files for the active scope.
- [ ] Modified files are listed as expandable accordion cards displaying file paths, addition badges, and deletion badges.
- [ ] A layout toggle allows switching between Unified hunk view and Split two-column side-by-side view.
- [ ] Split side-by-side view aligns unchanged, added, and deleted lines across columns with synchronized scrolling.
- [ ] Clean empty states render when no uncommitted changes or branch diffs exist.
- [ ] Diff endpoints and frontend components are covered by automated tests and adhere to the Universal File Line Budget (<= 500 lines).
