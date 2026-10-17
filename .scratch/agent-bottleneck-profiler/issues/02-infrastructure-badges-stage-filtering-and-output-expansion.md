# 02: Infrastructure Badges, Stage Filtering, and Output Expansion

**What to build:** Automatic infrastructure categorization and diagnostic exploration controls in the Bottlenecks tab. Every profiled operation is classified with color-coded infrastructure badges (`Package Install`, `Test Suite`, `Build / Compile`, `Git / VCS`, `LLM Thinking`). Developers can filter the list with stage pills (*All*, *Planner*, *Coder*, *Verifier*, *Reviewer*) and category toggles (*All*, *Commands*, *Thinking*). Clicking any item expands full execution details, including exit code, stdout/stderr with highlighted error lines, working directory, and collapsible reasoning text.

**Blocked by:** 01: In-Drawer Bottleneck Tab and Live Event Ranking

**Status:** ready-for-agent

- [ ] Automatic category classification identifies package installations, test runners, build steps, git commands, and LLM thinking blocks.
- [ ] Each bottleneck card displays its infrastructure category badge, stage badge, and exit code indicator (green for code 0, red for non-zero).
- [ ] Interactive stage filter pills allow filtering items by pipeline stage (*All*, *Planner*, *Coder*, *Verifier*, *Reviewer*).
- [ ] Category toggle buttons allow isolating shell commands vs LLM thinking phases.
- [ ] Expanding a command card displays working directory (`cwd`), full stdout/stderr with error lines highlighted, and command string.
- [ ] Expanding a thinking block displays the complete reasoning text with word wrap.
- [ ] Automated tests verify heuristic badge assignments, stage and category filtering, and accordion expansion.
