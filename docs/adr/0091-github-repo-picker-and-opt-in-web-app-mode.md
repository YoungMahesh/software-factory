# GitHub Repository Catalog Cache, Prime Repo Launch, and Opt-In Web App Mode

**Status**: Accepted (Amends [ADR 0089](0089-prompt-homepage-and-t3-launch-coordinator.md) and [ADR 0090](0090-prime-sandbox-multi-app-reuse.md)).

We extend the Sandbox Web Dashboard Builder (`sandboxes/sandbox/apps/` and `sandboxes/sandbox/static/index.html`) with a manually refreshed **Repository Catalog Cache** alongside the prompt box, Prime Sandbox support for cloning and opening existing GitHub repositories (with optional empty prompts via idle T3 threads), and an explicit `"web app"` toggle gating `run-app` prompt injection and dev-port allocation.

## Context

Under [ADR 0089](0089-prompt-homepage-and-t3-launch-coordinator.md) and [ADR 0090](0090-prime-sandbox-multi-app-reuse.md), the Builder homepage assumed every submission was a brand-new web application created from scratch (`create-app` Next.js template or blank Git workspace), and `build_initial_thread_prompt` unconditionally allocated a `dev_port` (`3001+`) and appended `run-app` browser-preview instructions to every prompt.

Developers also needed to open existing GitHub repositories from the Builder without:
1. Polling the GitHub REST API on every dashboard load or background refresh.
2. Paying full cold-start latency (`60–120s`) per repository when a compatible **Prime Sandbox** is already active.
3. Dirtying tracked repository files with automatic `package.json` port edits or triggering unwanted agent turns when simply opening a repository into T3 Code.

## Decisions

1. **Persisted Repository Catalog Cache with Manual-Only Refresh**:
   - Store the fetched repository list (`github-repos.json`: `org`, `refreshed_at`, and non-archived repositories under `GH_ORG_NAME`, excluding internal vault repositories `env-store` and `caddy-store`) in the existing `factory-state-v1` Modal Volume rather than browser `localStorage` or on-load API polling.
   - `GET /api/github/repos` serves strictly from the persisted cache; `POST /api/github/repos/refresh` is the sole path that contacts GitHub (`GH_TOKEN`), invoked only when the operator clicks the dedicated Refresh button.

2. **Isolated Prime Sandbox Cloning and Host-Side Secret Injection for Selected Repos**:
   - When a GitHub repository is selected (from the cached list or manual `owner/repo` input), the coordinator acquires or reuses the matching **Prime Sandbox** rather than booting a dedicated single-repo sandbox.
   - Each Builder launch clones shallow (`--depth 50`) on the target branch into its own isolated `/root/<slug>` directory (disambiguating `/root/<slug>-2`, etc.), injects `env-store` secrets, `.git/env-vault/`, and repo-local Git authorship host-side via `EnvStoreVault`, installs Node dependencies (`pnpm install` / `npm install`) when present, and skips Resource Plane PostgreSQL auto-provisioning so existing database configurations are preserved.

3. **Idle T3 Thread Creation on Empty Prompts and Opt-In `"web app"` Mode**:
   - Add a `"web app"` checkbox to the Builder controls bar (defaulting to checked for `Next.js App` scratch projects, and unchecked for `Blank Git Repo` or selected GitHub repositories).
   - Allocate `dev_port` (`3001+`) and append the `run-app` startup instruction **only** when `"web app"` is checked. For existing GitHub repositories with `"web app"` checked, `dev_port` is passed strictly through the `run-app` prompt without mutating or auto-committing tracked repository files.
   - When a GitHub repository is submitted with an empty prompt and `"web app"` unchecked, the coordinator creates an idle T3 thread directly (`thread.create` over T3's authenticated local WebSocket RPC, falling back to a brief generic prompt only if RPC fails) and opens `/<environmentId>/<encodedThreadId>#token=...`. When `"web app"` is checked with an empty prompt, a concise `run-app` prompt starts and previews the application.

## Considered Options

- **Store Cached Repo List in Browser `localStorage`**: Rejected so the catalog persists across browsers, devices, and control plane restarts alongside `apps/`, `launches/`, and `primes/` on `factory-state-v1`.
- **Boot Dedicated Single-Repo Sandbox per Selected Repository**: Rejected for Builder launches to preserve sub-second/few-second Prime Sandbox reuse; dedicated per-repo containers remain available in the **Sandboxes** tab launch modal.
- **Share `/root/<repo>` Across Multiple Builder Cards for the Same Repo**: Rejected because switching branches or clicking **Delete** (`cleanup_app_workspace`) on one card would clobber sibling cards.
- **Always Send a Generic Prompt on Empty-Prompt Repo Open**: Rejected when `"web app"` is unchecked because T3's `thread.create` command creates an idle thread without burning tokens or triggering an unwanted agent run.

## Consequences

- Opening an existing repository from the Builder takes only clone + dependency install time inside an active **Prime Sandbox** and produces zero tracked Git changes.
- Dashboard loads never trigger GitHub API rate limits or latency unless the operator clicks the repo Refresh button.
- Cloned repositories inside a shared **Prime Sandbox** share container CPU/RAM and lifetime with sibling apps in that container.
