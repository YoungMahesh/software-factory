# Launch Fresh Sandboxes from Control Plane Web UI

**Status**: Accepted (Amends [ADR 0065](0065-constant-modal-app-and-named-sandboxes.md), [ADR 0079](0079-hosted-sandbox-control-plane-function.md), [ADR 0084](0084-sandbox-runner-web-ui-and-snapshot-registry.md), and [ADR 0085](0085-retire-local-web-ui-and-enforce-basic-auth.md))

We introduce the capability to launch fresh sandboxes—both Repository Sandboxes and Standalone Sandboxes—directly through the Modal Sandbox Runner Control Plane Web UI (`sandbox/static/index.html`) backed by an authenticated REST endpoint (`POST /api/sandboxes` in `sandbox/web.py`).

## Context

Prior to this change, the Control Plane Web UI supported listing running sandboxes, terminating active sandboxes, capturing filesystem snapshots, and launching sandboxes from existing snapshot images (`POST /api/snapshots/{image_id}/launch`). However, launching fresh sandboxes required accessing the host terminal CLI (`sandbox/main.py`) or invoking the machine-to-machine headless API (`POST /launch`) using Bearer token authentication.

Per ADR 0085, machine-to-machine endpoints (`POST /launch`, `POST /snapshot`) use Bearer tokens (`MODAL_SANDBOX_AUTH_TOKEN`), while browser-based interactions on the Web UI use HTTP Basic Authentication (`WEB_UI_USERNAME`, `WEB_UI_PASSWORD`). Because no browser-authenticated endpoint existed for provisioning fresh sandboxes, operators managing sandboxes strictly through the web dashboard could not launch new workspaces without switching to a terminal or managing manual Bearer authorization headers.

## Decisions

1. **Authenticated REST Endpoint for Fresh Sandboxes (`sandbox/web.py`)**:
   - Expose `POST /api/sandboxes` mounted on the Web UI router and protected by HTTP Basic Authentication (`check_authentication`).
   - Define `FreshSandboxLaunchPayload` supporting both `mode="repo"` and `mode="standalone"`.
   - Validate input constraints:
     - `mode="repo"`: requires non-empty `repo` parameter.
     - `mode="standalone"`: requires non-empty `name` parameter.
   - Delegate provisioning directly to `sandbox.core.launch_sandbox()` and resolve workspace profiles via `sandbox.profiles.get_client_for_profile()`.
   - Return standard `LaunchResponse` containing connection metadata, SSH command, and agent URLs.

2. **Unified Launch Dialog in Web Dashboard (`sandbox/static/index.html`)**:
   - Add a primary `+ Launch Sandbox` action button in the Sandboxes tab header toolbar adjacent to the quick filter search input.
   - Provide a segmented mode switcher at the top of the modal between **Repository Sandbox** and **Standalone Sandbox**:
     - **Repository Mode**: displays `Target Repository` (`-r/--repo`, required), `Git Branch` (`-b`, default `main`), `App Name` (optional, auto-derived from repo slug if blank), `--testing` org checkbox, and `--full-clone` toggle.
     - **Standalone Mode**: displays `Sandbox App Name` (`--name`, required) for booting clean workspaces with an empty repository initialized at `/root/<name>`.
   - Provide shared options across both modes:
     - **Workspace Profile**: dropdown pre-selected to the currently active navbar profile (or active default if "All Profiles" is selected).
     - **Runtime Mode**: Linux VM Sandbox mode checkbox with memory input in GB (defaulting to 1 GB when enabled; Standard container runtime when unchecked).
     - **Integrated Tooling**: checkboxes for T3 Code Server (default enabled), OpenCode, Antigravity CLI, and Modal SDK tooling.
     - **Cloudflare Ingress**: enabled by default (`no_cloudflare=False`).

3. **Post-Launch Connection Details Feedback**:
   - On successful fresh launch, reuse the existing Connection Details dialog (`resultModalOpen`), presenting the live Sandbox ID, App Name, full SSH command snippet with copy button, and direct T3 Code Server and OpenCode URLs.
   - Dismissing the modal automatically refreshes the Sandboxes list.

## Consequences

- Operators can launch fresh repository-backed and standalone sandboxes entirely within the Web Dashboard across all configured Modal workspace profiles.
- Strict separation of authentication schemes (ADR 0085) is maintained: Web UI endpoints use HTTP Basic Auth, while headless machine-to-machine routes retain Bearer token authentication.
- All Python modules remain strictly under the universal <= 500 lines physical budget ratchet (ADR 0057 / AGENTS.md).
