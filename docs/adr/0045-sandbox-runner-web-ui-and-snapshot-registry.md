# Sandbox Web Dashboard, Snapshot Registry, and Multi-Profile Workspace Discovery

**Status**: Accepted (Amends [ADR 0024](0024-filesystem-snapshots-in-unified-sandbox-runner.md), [ADR 0003](0029-constant-modal-app-and-named-sandboxes.md), and [ADR 0040](0040-hosted-sandbox-control-plane-function.md))

We introduce a unified browser management dashboard (`sandbox/web.py`), a persistent snapshot catalog backed by `modal.Dict` (`sandbox/snapshots.py`), and multi-profile workspace discovery (`sandbox/profiles.py`) into the Hosted Sandbox Control Plane and local developer CLI.

## Context

Prior to this change, managing active Modal sandboxes required terminal commands (`scripts/manage_sandboxes.py`) or navigating Modal's generic web console. Inspecting sandboxes provisioned with custom tags, instance names, and forwarded ports lacked an integrated, visual dashboard.

Furthermore, filesystem snapshots captured via `--snapshot` recorded point-in-time container filesystems into `modal.Image`, but their image IDs and metadata (associated repository, description, timestamps, and size) were only printed to terminal logs without persistent indexing. Because Modal does not provide an image search API by tag or metadata, snapshot references were easily lost across developer sessions and machines.

Finally, developers often work across multiple Modal accounts and workspace profiles configured in `~/.modal.toml`. Discovering and terminating sandboxes or browsing snapshots in different profiles required manual shell environment switching (`MODAL_PROFILE=...`).

## Considered Options

- **Separate Full-Stack Web Application (Node/React/Next.js)**: Build an independent frontend dashboard hosted outside Modal (e.g. Vercel or cloud container). Rejected because it introduces external hosting dependencies, build toolchains (npm/vite), and separate credential synchronization away from the Python/Modal core codebase.
- **External Database for Snapshot Indexing (PostgreSQL/Turso)**: Store snapshot metadata in an external SQL database. Rejected to avoid third-party storage credentials and stateful database migrations for lightweight sandbox metadata that naturally belongs to the Modal workspace.
- **Embedded Single-Page Dashboard in Control Plane with `modal.Dict` Registry (Accepted)**:
  - Serve an embedded HTML5 single-page application (`sandbox/static/index.html`) directly through FastAPI (`sandbox/web.py`) with zero build step, dark/light theme, and live polling.
  - Store snapshot metadata in a named `modal.Dict` (`sandbox-snapshots`) with an automatic local JSON file fallback (`~/.modal/sandbox-snapshots.json`) when operating without active cloud Dict access.
  - Expose workspace profile inspection and client scoping (`sandbox/profiles.py`) by parsing `~/.modal.toml`, allowing users to query and switch workspaces from the UI or REST API.
  - Provide a standalone launcher script (`scripts/web_ui.py`) and mount the web routes directly onto the deployed cloud control plane (`sandbox/function.py`).

## Architecture & Components

### 1. Web UI & REST Endpoints (`sandbox/web.py`)

- **Frontend Delivery**: Serves `sandbox/static/index.html` at `GET /` and `/ui`.
- **REST Endpoints**:
  - `GET /api/sandboxes`: Lists active sandboxes across specified or active profiles with metadata (sandbox ID, app, state, instance name, created at).
  - `DELETE /api/sandboxes/{sandbox_id}`: Terminate a running sandbox.
  - `GET /api/snapshots`: Lists recorded filesystem snapshots from the registry.
  - `POST /api/snapshots`: Captures a snapshot from a running sandbox and registers its metadata.
  - `DELETE /api/snapshots/{snapshot_id}`: Removes snapshot metadata from the registry.
  - `GET /api/profiles`: Lists configured Modal profiles and identifies the active default.
  - `POST /launch`: Synchronous sandbox launch endpoint (delegating to `sandbox/core.py`).
  - `GET /health`: Health and readiness probe.

### 2. Snapshot Registry & Retention (`sandbox/snapshots.py`)

- **Named Dict Persistence**: Uses `modal.Dict.from_name("sandbox-snapshots", create_if_missing=True)` to persist snapshot records containing:
  - `snapshot_id`: Canonical snapshot identifier.
  - `image_id`: Modal image identifier for container resurrection (`--from-snapshot`).
  - `description`: Human-readable label or purpose.
  - `created_at`: ISO 8601 UTC timestamp.
  - `ttl_days` / `ttl_seconds`: Expiration horizon matching Modal image retention.
  - `tags`: Key-value tags including repository provenance and author.
- **Local Fallback**: Automatically falls back to reading/writing `~/.modal/sandbox-snapshots.json` when cloud Dict access is unavailable.
- **Snapshot Retention & Invariant Pruning**: To prevent displaying unlaunchable snapshot images, snapshot records are bounded by TTL and pruned when underlying image references expire or become unavailable.

### 3. Multi-Profile Workspace Discovery (`sandbox/profiles.py`)

- Parses `~/.modal.toml` using Python's standard `tomllib` without invoking shell subshells or exposing secrets.
- Maintains an in-memory client cache (`_CLIENT_CACHE`) of authenticated `modal.Client` instances keyed by profile name.
- Enables multi-tenant sandbox enumeration and administration from a single dashboard instance.
- **Ambient Cloud Fallback**: When deployed in cloud container environments lacking `~/.modal.toml`, profile resolution degrades gracefully to the ambient execution client (`modal.Client.from_env()`) with a default profile label, avoiding parsing errors while restricting multi-profile switching to local environments.

### 4. Sandbox Lifecycle Extraction (`sandbox/lifecycle.py`)

- Centralizes sandbox discovery, instance name extraction (inspecting tags, Antigravity logs, and configs), and termination routines into a reusable module shared between `sandbox/web.py` and `scripts/manage_sandboxes.py`.

## Consequences

- Developers can visually manage sandboxes and snapshots via `python3 scripts/web_ui.py` or the hosted cloud control plane endpoint.
- Captured snapshots are permanently indexed and searchable by description and tags, preventing lost image identifiers.
- Multi-workspace switching is seamless locally, while cloud deployments operate reliably under ambient authentication.
- All modules remain strictly within the universal <= 500 lines budget ratchet (ADR 0027 / AGENTS.md).
