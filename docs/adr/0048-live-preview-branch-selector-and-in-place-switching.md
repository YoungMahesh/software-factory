# Live Preview Branch Selector and In-Place Container Switching

**Status**: Accepted (Amends [ADR 0034](0034-factory-studio-and-live-preview-workspace.md) and [ADR 0038](0038-unified-studio-sandbox-for-live-preview-and-agent-execution.md))

To allow developers to toggle between `main` and active feature branches without container teardown latency, we decided to transform the read-only active branch badge in the Live Preview toolbar into an interactive **Live Preview Branch Selector**, powered by in-place `sandbox.exec` Git orchestration and dependency drift resolution.

## Considered Options

- **Static Pill with Container Stop / Restart**: Forcing developers to stop the preview sandbox and launch on a different branch. Rejected because container provisioning incurs 30–60s cold-start latencies and destroys rapid visual comparison workflows.
- **Top Control Bar Global Branch Selector**: Placing branch switching alongside repository selection in the top navigation bar. Rejected because branch switching specifically controls the preview application environment and dev server context, which belongs directly in the Live Preview toolbar next to the viewport controls.
- **Unfiltered All-Branch Dropdown**: Displaying all remote branches from GitHub. Rejected because software factory workflows center strictly on `main` (trunk) and `factory/<feature>` or `factory/issue-<id>` branches; showing unrelated or stale branches creates confusion.
- **In-Place `sandbox.exec` with Diff-Aware Dependency Installation**: Executing `git reset --hard && git clean -fd && git checkout <branch> && git pull origin <branch>` inside the running container and executing `pnpm install --prefer-offline` only when `package.json` or `pnpm-lock.yaml` diffs are detected. Accepted.

## Consequences

- The canonical term **Live Preview Branch Selector** is recorded in `CONTEXT.md`.
- **Backend GitHub API Extensions (`factory/ui/github.py` & `factory/ui/app.py`)**:
  - `GET /api/studio/repos/{repo}/branches`: Fetches remote branches for the repository, filtering to `main` (or default branch) and active `factory/*` branches.
  - `POST /api/studio/repos/{repo}/preview/branch`: Validates target branch, executes clean in-place checkout inside the active Unified Studio Sandbox (`sandbox.exec`), runs `pnpm install` if dependencies changed, updates `PreviewRegistry` branch tracking, and broadcasts SSE `branch` and `preview_refresh` events.
  - If the preview sandbox is currently stopped/idle, updates the repository's target preview branch so the next launch begins on that branch.
- **Concurrency & Safety Guards**:
  - Branch switching is strictly disabled with a visual lock/tooltip when an Assembly Line Pipeline job is active (`RUNNING` or `QUEUED`) to prevent race conditions during autonomous code generation.
- **Fault-Tolerant Non-Destructive Failure Recovery**:
  - If `git fetch`, checkout, or package installation fails in-container, stderr is appended to preview dev server logs with diagnostic details, the container is preserved on its previous branch without termination, and an error alert is returned to the UI.
- **Frontend Reactive UI (`factory/ui/frontend/src/components/LivePreview.tsx`)**:
  - Replaces static `#preview-branch-badge` with an interactive dropdown menu displaying the current branch, a list of available remote branches, active checkmark, and a loading spinner during transitions.
