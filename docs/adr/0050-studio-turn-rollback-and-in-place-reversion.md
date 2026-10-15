# Studio Turn Rollback and In-Place Reversion

**Status**: Accepted (Amends [ADR 0034](0034-factory-studio-and-live-preview-workspace.md), [ADR 0038](0038-unified-studio-sandbox-for-live-preview-and-agent-execution.md), and [ADR 0047](0047-factory-studio-pull-request-visibility-and-merge-controls.md))

To enable rapid frontend design exploration when an experimental agent turn produces unwanted visual or layout changes, we decided to implement **Turn Rollback** in Factory Studio via safe linear `git revert` orchestration inside the Unified Studio Sandbox (`sandbox.exec`), automatic issue tracker reopening, diff-aware dev server dependency synchronization, and append-only Studio Chat History tracking.

## Considered Options

- **Destructive Git History Reset (`git reset --hard` + Force Push)**: Rewinding the branch ref and force-pushing to remote GitHub. Rejected because it destroys history permanently, causes synchronization failures if remote refs are pulled or protected, and prevents auditability.
- **Selective Out-of-Order Cherry-Pick Reverts**: Allowing developers to revert an arbitrary historical turn while preserving subsequent turns. Rejected because frontend component diffs frequently create unresolvable merge conflicts when applied out of order without human intervention.
- **Container Teardown and Reprovisioning**: Terminating the Unified Studio Sandbox and starting a new container from an earlier commit. Rejected because container cold starts take 30–60s, destroying the rapid feedback loop required for visual exploration.
- **Destructive Chat Message Pruning**: Deleting user prompts and assistant responses from the database. Rejected because it destroys reasoning telemetry logs and diagnostic audit trails.
- **Safe Linear Revert with In-Place Container Synchronization & Issue Reopening**: Creating a forward `git revert` commit in the running container via `sandbox.exec`, pushing to `origin/<branch>`, executing diff-aware `pnpm install`, reopening the associated issue on the issue tracker, and persisting an append-only `Turn Rollback Card` in Studio Chat History. Accepted.

## Consequences

- The canonical term **Turn Rollback** is recorded in `CONTEXT.md`.
- **Backend Rollback Endpoint (`factory/ui/app.py` & `factory/ui/registry.py`)**:
  - `POST /api/studio/repos/{repo}/turns/rollback`:
    - Validates target turn or defaults to the latest completed code-producing turn on the active branch.
    - Strictly rejects (HTTP 409) if an Assembly Line Pipeline job is active (`RUNNING` or `QUEUED`).
    - Strictly rejects (HTTP 400) if the Feature Pull Request has already been merged into `main` via In-Studio Merge Control.
    - Ensures Unified Studio Sandbox is running (auto-launches if stopped).
    - Executes in-container clean `git revert --no-edit <commit_sha>` and `git push origin <branch>` via `sandbox.exec`.
    - If `git revert` encounters conflicts, immediately runs `git revert --abort`, leaves the working tree clean, streams diagnostic stderr to logs, and returns HTTP 400.
    - Checks for `package.json` or `pnpm-lock.yaml` diffs against parent commit; if present, runs `pnpm install --prefer-offline`.
    - Broadcasts SSE `preview_refresh` event to trigger immediate Vite HMR or iframe reload.
- **Issue Tracker & Pull Request Coordination**:
  - For GitHub Issues: Reopens the associated issue, resets label to `ready-for-agent`, and posts an automated comment explaining the rollback. The Feature Pull Request automatically reflects the revert commit in its diff.
  - For Local Markdown Issue Tracker: Resets ticket status to `ready-for-agent` and strips the resolved commit line in `.scratch/<feature>/`.
- **Durable Studio Chat History Representation (`factory/ui/db.py`)**:
  - Updates the original message's `turn_data_json` with `{ "reverted": true, "reverted_at": <ts>, "revert_commit": "<sha>" }`.
  - Appends a new conversational message with `role: "assistant"` and `turn_data: { "type": "turn_rollback", ... }` rendering an explicit `Turn Rollback Card`.
- **Frontend Reactive UI (`factory/ui/frontend/`)**:
  - Adds an inline "Undo Turn" button on the Delivery Gate Card / Assistant Response Card for completed unmerged turns.
  - Adds an "Undo Last Turn" button in the Live Preview toolbar and Prompt Composer bar.
  - Displays a confirmation modal detailing the issue title, commit SHA, and rollback consequences before execution.
  - Visually marks reverted turn cards with a `Reverted` status badge and disables duplicate approvals or merges.
