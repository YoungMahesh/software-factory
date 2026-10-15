# Factory Studio Pull Request Visibility and Merge Controls

**Status**: Accepted (Amends [ADR 0033](0033-github-issues-and-pull-requests-for-feature-delivery.md) and [ADR 0034](0034-factory-studio-and-live-preview-workspace.md))

To close the visibility gap where the Assembly Line manages GitHub Feature Pull Requests but Factory Studio lacks UI to observe or merge them, we decided to introduce native Feature Pull Request visibility across the top control bar and conversational timeline, coupled with in-Studio squash merge controls and automated Unified Studio Sandbox synchronization to `main`.

## Considered Options

- **Top Control Bar Only**: Placing PR links and merge buttons strictly in the top navigation header. Rejected because it detaches delivery completion from the conversational flow and lacks space for rich ticket resolution breakdowns.
- **Chat Timeline Only**: Rendering PR information only as completion cards in the chat history. Rejected because once the user scrolls or performs subsequent turns, PR visibility and quick merge access are lost.
- **Dual Placement (Control Bar Pill + Timeline Delivery Gate Card)**: Persistent status badge and merge action in the top control bar alongside an interactive reactive Delivery Gate Card in the chat timeline and PR status indicators in the Issue Drawer milestone headers. Accepted.
- **Direct Merge Commit or Rebase**: Creating a standard merge commit or rebasing. Rejected in favor of GitHub Squash Merge (`merge_method: "squash"`) because intermediate agent attempts, verifier fixes, and telemetry commits produce noisy history; squash merging with explicit `Fixes #<id>` headers yields a clean trunk log on `main` and automatically closes all linked GitHub issues.
- **Preview Sandbox Teardown Post-Merge**: Stopping the Unified Studio Sandbox container upon merge. Rejected because tearing down the preview forces developers to cold-start a new sandbox to verify the merged application on `main`. Executing in-sandbox `git reset --hard && git clean -fd && git checkout main && git pull origin main` via `sandbox.exec` seamlessly updates the live dev server without container downtime.

## Consequences

- The canonical terms **Delivery Gate Card** and **In-Studio Merge Control** are incorporated into `CONTEXT.md`.
- **Backend GitHub API Extensions (`factory/ui/github.py` & `factory/ui/app.py`)**:
  - `GET /api/studio/repos/{repo}/pulls`: Lists active and recent Feature Pull Requests for the selected repository, resolving the active PR matching the active feature branch (`factory/<feature>`) or latest open `factory/*` branch.
  - `POST /api/studio/repos/{repo}/pulls/{pull_number}/merge`: Executes a GitHub squash merge passing formatted `commit_title` (`${pr.title} (#${pr.number})`) and `commit_message` containing resolved ticket `Fixes #...` directives, deletes the remote feature branch, and triggers post-merge sandbox synchronization.
- **In-Sandbox Pipeline Telemetry (`sandbox/factory/pipeline.ts`)**:
  - Emits structured `delivery_gate` telemetry envelopes over the Agent Event Stream when `initializeDeliveryGate` (Draft PR created) and `finalizeDeliveryGate` (PR marked Ready for Review) are invoked.
- **Frontend UI & Reactive Components**:
  - **Top Control Bar**: Renders a dedicated PR status button (`Draft`, `Ready for Review`, `Merged`, `Conflict`) with a direct GitHub link and a merge confirmation popover.
  - **Chat Timeline**: Renders a reactive `DeliveryGateCard` summarizing resolved work items, verifier status, PR links, and an inline "Merge into main" button.
  - **Issue Drawer**: Milestone headers render associated PR badges and links.
- **Live Sandbox Synchronization**:
  - When a PR is successfully merged, the active Unified Studio Sandbox executes a clean checkout of `main` via `sandbox.exec`, updating the preview branch state and reflecting the merged application in the Live Preview iframe.
- **Merge Gate Safety**:
  - Merging is strictly disabled while the PR is in `Draft` state or while the Assembly Line is actively executing.
  - If GitHub reports `mergeable: false`, the control indicates a `Conflict` badge with a direct link to GitHub's conflict resolution interface.
