# 01: In-Drawer Bottleneck Tab and Live Event Ranking

**What to build:** A dedicated "Bottlenecks" tab in the Factory Studio Activity Drawer that extracts all executed bash commands, verifier test runs, and LLM thinking blocks from real-time and historical job telemetry events. The view ranks every operation strictly from longest to shortest duration with visual duration bars, displays an active execution banner for any currently running command, and provides a toggle to hide micro-commands under 100ms.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] A fourth tab button `Bottlenecks` (`id="btn-drawer-tab-bottlenecks"`) is visible in the Activity Drawer alongside Timeline, Terminal Logs, and History.
- [ ] A modular component renders the bottleneck list, keeping parent drawer line count strictly <= 500 lines.
- [ ] Completed bash commands, verifier runs, and LLM thinking sessions are extracted from job telemetry events and sorted in descending order of `durationMs`.
- [ ] Each bottleneck row displays its rank (#1, #2, ...), operation title, duration in seconds/ms, and relative duration bar.
- [ ] When a command or tool is actively executing, an active banner with a running spinner is displayed at the top of the tab.
- [ ] A toggle control allows developers to hide or reveal micro-commands that executed in less than 100ms.
- [ ] Automated tests verify tab switching, descending duration sorting, active spinner display, and threshold filtering.
