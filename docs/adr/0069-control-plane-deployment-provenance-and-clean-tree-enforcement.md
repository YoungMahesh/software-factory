# Control Plane Deployment Provenance and Clean Working Tree Enforcement

**Status**: Accepted (Amends [ADR 0040](0040-hosted-sandbox-control-plane-function.md), [ADR 0045](0045-sandbox-runner-web-ui-and-snapshot-registry.md), and [ADR 0059](0059-sandbox-software-factory-commit-provenance.md))

We establish deployment Git commit provenance tracking and clean working tree enforcement for the hosted Modal Sandbox Control Plane (`sandbox/function.py`), surfacing the deployed Git commit hash directly in the Web UI dashboard header and failing deployment fast if uncommitted local edits are present.

## Context

The Modal Sandbox Control Plane is a serverless application combining a FastAPI REST API and an Alpine.js single-page dashboard (`sandbox/web.py` and `sandbox/static/index.html`) deployed to Modal cloud via `modal deploy` or `modal serve sandbox/function.py`.

Prior to this decision:
1. **Opaque Deployment Version**: While child sandboxes tracked their container image provenance via ADR 0059 (`/etc/software-factory-version.json`), the running control plane function had no visual indicator of its own Git deployment revision. Because Modal functions run a serverless snapshot of the codebase uploaded at deployment time, developers modifying `software-factory` could not determine from the browser dashboard whether the running control plane contained their latest Git commits or an older release without checking external Modal CLI logs.
2. **Silent Uncommitted Drift**: Running `modal deploy` or `modal serve` with dirty working trees (uncommitted changes) would package uncommitted local state into the cloud function. This led to ambiguous deployment states where the running function behavior deviated from clean Git history without any trace or warning.

## Decisions

1. **Clean Working Tree Enforcement (`validate_clean_working_tree`)**:
   - In `sandbox/function.py`, introduced `validate_clean_working_tree(repo_root)` executed at module initialization during deployment.
   - If `resolve_host_software_factory_provenance(root)` detects uncommitted local changes (`SOFTWARE_FACTORY_DIRTY == "1"`), deployment halts immediately with a descriptive `RuntimeError`:
     `"Cannot deploy sandbox control plane with uncommitted changes. Please commit or stash your changes before running 'modal deploy' or 'modal serve', or set ALLOW_DIRTY_DEPLOY=1 to bypass."`
   - Bypassed automatically during test runs (`pytest` in modules or `PYTEST_CURRENT_TEST` in environment) unless explicitly tested with `enforce=True`, and respects `ALLOW_DIRTY_DEPLOY=1` as an emergency developer override.

2. **Deploy-Time Provenance Capture**:
   - In `collect_control_plane_secrets(root)` in `sandbox/function.py`, host Git provenance metadata (`SOFTWARE_FACTORY_COMMIT`, `SOFTWARE_FACTORY_COMMIT_SHORT`, `SOFTWARE_FACTORY_REF`, `SOFTWARE_FACTORY_DIRTY`) resolved via `resolve_host_software_factory_provenance` is injected into `modal.Secret`.
   - When the function executes in Modal cloud, the deployed commit metadata is natively available in the container process environment (`os.environ`).

3. **REST API Endpoint (`GET /api/version`)**:
   - In `sandbox/web.py`, added `GET /api/version` returning structured provenance metadata (`commit`, `commit_short`, `ref`, `dirty`).
   - Protected by standard HTTP Basic Authentication (`check_authentication`).

4. **Web UI Header Plain Text Monospace Badge**:
   - In `sandbox/static/index.html`, added a styled monospace pill badge directly beside the `[Control Plane]` badge in the navbar:
     `<span x-show="version && version.commit_short && version.commit_short !== 'unknown'" class="text-xs px-2 py-0.5 rounded-full bg-slate-800 text-slate-300 font-mono" x-text="'git: ' + version.commit_short"></span>`
   - Rendered as plain text without click-to-copy or external links.
   - Alpine.js fetches `/api/version` on initialization (`init()`). If version metadata is unavailable or unknown, the badge remains hidden.

## Consequences

- Developers inspecting the control plane Web UI can immediately identify the exact Git commit of `software-factory` running in Modal cloud.
- Uncommitted local edits cannot accidentally be deployed to production, preventing hidden behavioral regressions.
- Developers retain an emergency escape hatch via `ALLOW_DIRTY_DEPLOY=1` when rapid prototyping is necessary.
- Universal File Line Budget (ADR 0027 / AGENTS.md) is preserved across all modified files.
