# Cross-App Sandbox Discovery and Environment-Wide Listing in Control Plane Web UI

**Status**: Accepted (Amends [ADR 0065](0065-constant-modal-app-and-named-sandboxes.md), [ADR 0079](0079-hosted-sandbox-control-plane-function.md), and [ADR 0084](0084-sandbox-runner-web-ui-and-snapshot-registry.md))

We transition the Modal Sandbox Runner Control Plane Web UI (`sandbox/web.py` and `sandbox/static/index.html`) from repository-scoped sandbox filtering (`target_app = "software-factory"`) to environment-wide discovery (`all_apps=True`). We enrich sandbox lifecycle inspection (`sandbox/lifecycle.py`) to resolve logical Modal App names across both freshly provisioned and snapshot-restored sandboxes.

## Context

In ADR 0065, we adopted the constant Modal App model where repository sandboxes are grouped under a project-level App (e.g., `software-factory`), while standalone launches and snapshot restorations define custom or generated App names via `--name` (e.g., `resumed-sandbox`, `resumed-<image_id>`).

In ADR 0084, we introduced the Control Plane Web UI to discover and manage sandboxes across workspace profiles. However, the Web UI API endpoint `GET /api/sandboxes` inherited the default behavior of CLI tooling (`scripts/manage_sandboxes.py`), defaulting `all_apps=False`. Inside `sandbox/lifecycle.py`, queries without `all_apps=True` fell back to `target_app = "software-factory"` and looked up `modal.Sandbox.list(app_id=<software-factory-id>)`.

Consequently:
1. Freshly created sandboxes provisioned with `--repo software-factory` matched the `software-factory` App ID and were displayed in the web dashboard.
2. Sandboxes launched from snapshots (which run under independent App names like `resumed-sandbox` or `resumed-<image_id>`) were completely excluded by Modal's server-side `app_id` filter.
3. When `all_apps=True` was used, `sandbox/lifecycle.py` attempted to access `getattr(sb, "app_id", None)` on `modal.Sandbox` objects. Because Modal SDK sandbox handles store the internal App ID on `_app_id`, the field returned `None` and displayed as `"default-app"` in the UI.

## Decisions

1. **Default Environment-Wide Discovery for Web UI (`sandbox/web.py`)**:
   - `api_list_sandboxes` now defaults `all_apps: bool = Query(True)`.
   - If a caller explicitly supplies `app_name`, `effective_all_apps` evaluates to `False` to preserve targeted app filtering.
   - If a caller explicitly passes `all_apps=false` without `app_name`, it retains the fallback to `"software-factory"`.

2. **Explicit Web UI Query Flag (`sandbox/static/index.html`)**:
   - The dashboard single-page application explicitly appends `all_apps=true` to all `/api/sandboxes` queries in `refreshAll()`, ensuring transparent and defensive cross-app discovery regardless of server defaults.

3. **Logical App Name and Tag Resolution (`sandbox/lifecycle.py` & `sandbox/core.py`)**:
   - `sandbox/core.py` tags all newly launched sandboxes with `tags={"instance_name": sandbox_name, "app_name": app_name}`.
   - `sandbox/lifecycle.py` introduces `resolve_app_name(sb, fallback=...)`, which inspects tags first, falls back to reading `MODAL_APP_NAME` from running container environment variables, and finally defaults to `getattr(sb, "app_id", getattr(sb, "_app_id", None))`.
   - In cross-app listing mode (`all_apps=True`), the UI displays the true application name (`resumed-sandbox`, `software-factory`, etc.) instead of fallback placeholders.

## Consequences

- The Control Plane Web UI displays all active sandboxes in the workspace—whether freshly launched from repositories, resumed from point-in-time filesystem snapshots, or launched standalone.
- All lifecycle management actions in the UI (Snapshot capture, SSH connection copying, and Sandbox termination) function uniformly across all sandbox types.
- CLI scripts (`scripts/manage_sandboxes.py`) preserve backwards compatibility, maintaining scoped filtering by default unless `--all-apps` is explicitly specified.
- All modified modules strictly adhere to the universal <= 500 lines budget ratchet (ADR 0057 / AGENTS.md).
