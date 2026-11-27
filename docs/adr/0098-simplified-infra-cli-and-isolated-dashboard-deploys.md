# ADR 0098: Simplified `modal-sandbox infra` CLI and Isolated Dashboard Self-Deploy

**Status**: Accepted (Amends [ADR 0082](0082-strict-resource-plane-deployment-configuration-and-idempotency.md), [ADR 0083](0083-mandatory-resource-plane-ssh-key-and-secrets-directory.md), [ADR 0085](0085-host-ingress-proxy-in-opt-caddy.md), [ADR 0086](0086-host-ingress-store-for-opt-caddy.md), [ADR 0092](0092-host-sandbox-dashboard-on-base-domain.md), and [ADR 0096](0096-nextjs-sandbox-dashboard-and-bff.md)).

We simplify `modal-sandbox infra` around canonical `.env` configuration and explicit subcommands, split the **Sandbox Web Dashboard** VPS runtime into isolated apex (`/opt/sandbox-dashboard`) and staging (`/opt/sandbox-dashboard-staging`) stacks, and add opposite-target deploy buttons in the dashboard header backed by an async **Hosted Sandbox Control Plane** worker.

## Context

Three friction points emerged across the VPS infrastructure CLI and dashboard deployment workflow:

1. **Flag sprawl and implicit behavior**: `modal-sandbox infra` accumulated standalone aliases (`deploy-infra`, `setup-caddy`), duplicated SSH/directory overrides (`--host`, `--user`, `--port`, `--key`, `--remote-dir`), redundant env/store toggles (`--no-sync-env`, `--sync`, `--from-store`, `-o`, `-t`, `--dir`, `--from-dir`), a `--profile` flag colliding with Modal workspace profiles, implicit `RESOURCE_PLANE_DOMAIN` fallback in `infra caddy`, and legacy apex dashboard flags (`--dashboard`, `--dashboard-upstream`, `--dashboard-web-upstream`, `--no-dashboard`) superseded by `infra dashboard`.
2. **Staging broke production under single-container deployment**: [ADR 0096](0096-nextjs-sandbox-dashboard-and-bff.md) deployed a single `/opt/sandbox-dashboard` container (`sandbox-dashboard-web:3000`) and required `--cutover` or `--subdomain <label>`. Testing broken dashboard changes on `dashboard.<APPS_BASE_DOMAIN>` overwrote that shared container and broke the apex `<APPS_BASE_DOMAIN>`.
3. **Self-restart deadlock from browser triggers**: Deploying `dashboard/` from inside `sandbox-dashboard-web` cannot access the VPS Docker socket, `/opt/caddy`, or SSH keys, and rebuilding the active container mid-request severs the HTTP connection.

## Decisions

1. **Canonical `modal-sandbox infra` CLI**:
   - Remove implicit `deploy` on bare `modal-sandbox infra` (printing subcommand help for `deploy`, `dashboard`, and `caddy`) and remove standalone `deploy-infra` and `setup-caddy` entrypoints from `pyproject.toml`. Also list `infra`, `create-app`, and `deploy-app` in `modal-sandbox --help`.
   - Remove `--host`, `--user`, `--port`, `--key`, and `--remote-dir` (`RESOURCE_PLANE_REMOTE_DIR`) across all `infra` subcommands; `/opt/resource-plane`, `/opt/sandbox-dashboard`, `/opt/sandbox-dashboard-staging`, and `/opt/caddy` are canonical and read `RESOURCE_PLANE_SSH_*` from `.env`.
   - Narrow subcommand options to active workflows:
     - `infra deploy`: `--check-only` only (removing `--no-sync-env`).
     - `infra dashboard`: `--subdomain` boolean flag only (removing `--cutover`, `--check-only`, `--control-plane-url`, `--base-domain`, `--cf-dns-token`, `--sync`, `--profile`).
     - `infra caddy`: `--domain`, `--s3-domain`, `--bootstrap`, `--email`, `--wildcard`, `--check-only` (removing `--upstream`, `--s3-upstream`, `--base-domain`, `--cf-dns-token`, `--dashboard*`, `--no-dashboard`, `--no-sync-env`, `--from-store`, `--sync`, `--profile`). Require explicit `--domain` to write `resource-plane.caddy` and normalize schemes/slashes.
     - `infra caddy backup|restore`: `--profile` only (plus `--prune` and `--bootstrap` on `restore`; removing `-o/--org`, `-t/--token`, `--dir`, `--from-dir`).

2. **Isolated Apex & Staging Dashboard Stacks**:
   - `modal-sandbox infra dashboard` deploys `/opt/sandbox-dashboard` (`sandbox-dashboard-web:3000`, Compose project `sandbox-dashboard`) and configures Caddy split apex routing on `https://<APPS_BASE_DOMAIN>` (routing `/launch`, `/snapshot`, `/health`, and `/api/codex/profiles` to Modal), leaving staging untouched.
   - `modal-sandbox infra dashboard --subdomain` deploys `/opt/sandbox-dashboard-staging` (`sandbox-dashboard-staging-web:3000`, Compose project `sandbox-dashboard-staging`) and exposes `https://dashboard.<APPS_BASE_DOMAIN>`, leaving the apex container and route untouched (keeping Modal CLI routes active at apex with HTTP `404` for browser paths when apex has not been deployed).
   - Bake each dashboard container's Git commit SHA into the UI (`NEXT_PUBLIC_DASHBOARD_COMMIT`) alongside the Modal Control Plane commit badge.

3. **Control-Plane-Backed Opposite-Target UI Deploy Buttons**:
   - Add an async endpoint and Modal worker in `sandboxes/sandbox/function.py` (installing `openssh-client`, `git`, and `tar`) that clones `main` from `${GH_ORG_NAME}/software-factory` via `GH_TOKEN` and executes `deploy_dashboard()` over SSH to the requested target (`apex` or `subdomain`).
   - Inject `RESOURCE_PLANE_SSH_PRIVATE_KEY` from the `RESOURCE_PLANE_SSH_KEY` file into the Control Plane Modal Secret at `modal deploy` time, with runtime fallback to decrypting `config/env/software-factory/resource_plane_ssh` via `AGE_PRIVATE_KEY`; child sandbox launch allowlists (`sandbox/launcher.py`) do not forward this key.
   - Render only the opposite target's deploy button in the `DashboardShell` header (`https://<APPS_BASE_DOMAIN>` shows only **Deploy → `dashboard.<APPS_BASE_DOMAIN>`**; `https://dashboard.<APPS_BASE_DOMAIN>` shows only **Deploy → `<APPS_BASE_DOMAIN>`**; `localhost` shows both) with confirmation and async status polling. Both buttons deploy `dashboard/` and Caddy routing only, leaving `modal deploy sandboxes/sandbox/function.py` on CLI/CI.

## Considered Options

- **Single shared container with exclusive Caddy routing**: Rejected because pushing broken changes to `dashboard.<APPS_BASE_DOMAIN>` overwrites the container serving `<APPS_BASE_DOMAIN>`.
- **Privileged VPS host daemon / Docker socket sidecar**: Rejected to avoid introducing and maintaining a second host-level control daemon alongside Modal Control Plane.

## Consequences

- Staging verification on `dashboard.<APPS_BASE_DOMAIN>` is isolated from `<APPS_BASE_DOMAIN>`, and neither dashboard container restarts itself when triggering a deployment of the other.
- Operators running `modal deploy sandboxes/sandbox/function.py` authorize the Control Plane to deploy `dashboard/` over SSH without exposing VPS keys inside child sandboxes.
