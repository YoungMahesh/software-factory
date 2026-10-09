# Issue 04: HTML UI Templates, Tailwind Layout, and SSE Consumer

Status: resolved

## Objective
Implement `factory/ui/templates/index.html` featuring a split-pane layout with Tailwind CSS:
- Left pane: Launch controls (Test Org banner, Repo selector with refresh, Feature input/dropdown, Issue ID, Model selector, VM toggle, Launch button).
- Main center pane: Stage stepper progress indicators, active run status, live auto-scrolling dark terminal viewer with ANSI color rendering, log search, and copy-to-clipboard.
- Bottom pane: Session run history table.

## Acceptance Criteria
- CDN-loaded Tailwind CSS (zero host Node/npm dependencies).
- SSE consumer connecting to `/api/jobs/{job_id}/stream` to display real-time terminal logs and animate stage progress.
- Clean responsive layout with interactive error reporting.
