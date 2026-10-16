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

## Addendum: Telemetry Contract Normalization, Mode A Gate Finalization, and In-Studio Draft PR Promotion

- **Telemetry Contract Normalization**:
  - `delivery_gate` telemetry events emitted over the `Agent Event Stream` canonicalize `pull_number` alongside backward-compatible aliases (`pull_request_number`, `pullRequestNumber`).
  - `DeliveryGateCard` resolves pull request identifiers across all supported aliases (`pull_number`, `pull_request?.number`, `pull_request_number`, `pullRequestNumber`), rendering explicit warning banners if the identifier is unresolvable and preventing silent interaction failures.
- **Mode A Single-Issue Gate Finalization**:
  - When the Assembly Line Pipeline executes in Mode A targeting a specific issue (`--issue <id>`), gate finalization evaluates the targeted issue resolution rather than requiring the entire milestone, converting the Feature Pull Request from Draft to Ready for Review once verification and review pass.
  - Milestone slugification in `GitHubClient.getMilestone` enforces alphanumeric normalization (`replace(/[^a-z0-9]+/g, "-")`) to reliably match complex milestone titles (e.g. `v1: Initial App` matching `v1-initial-app`).
- **In-Studio Draft PR Promotion**:
  - While a PR remains in Draft, `getPullRequestStatus` strictly evaluates `gateData?.draft`, preventing premature presentation of merge controls.
  - An inline `"Mark Ready for Review"` action on the `DeliveryGateCard` executes GitHub GraphQL mutation `markPullRequestReadyForReview` via `POST /api/studio/repos/{repo}/pulls/{pull_number}/ready_for_review`, allowing developers to promote draft pull requests directly within Factory Studio without switching to GitHub.

