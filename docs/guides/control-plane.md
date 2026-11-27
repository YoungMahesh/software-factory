# Hosted Sandbox Control Plane & Dashboard

The **Hosted Sandbox Control Plane** is a FastAPI backend and Launch Coordinator hosted on Modal (`sandboxes/sandbox/function.py`). The **Sandbox Web Dashboard** is its Next.js 16 + React 19 browser interface and same-origin BFF proxy (`dashboard/apps/web`), deployed to the VPS at `/opt/sandbox-dashboard`. The backend launches Development Sandboxes through the same launcher used by the local CLI. The **Resource Plane Console** and **Resource Plane Management API** manage persistent application resources separately. See [ADR 0096](../adr/0096-nextjs-sandbox-dashboard-and-bff.md).

## Configuration and deployment

Install the factory requirements, authenticate the launch host with Modal, and set both required dashboard credentials in the factory root `.env` or process environment:

```env
WEB_UI_USERNAME=admin
WEB_UI_PASSWORD=replace-with-a-strong-password
```

There is no implicit dashboard username. Missing credentials stop deploy/serve. Repository launches also require `GH_TOKEN`, with `GH_ORG_NAME` for shorthand names. Deployment warns about missing GitHub or Age credentials; `MODAL_ENFORCE_AUTH=1` makes missing GitHub access a deployment error. Standalone launches do not require GitHub access.

Configure provider tokens, `MODAL_TOKENS`, vault decryption, and ingress credentials for the capabilities you intend to expose. `--modal` inside child sandboxes requires valid `MODAL_TOKENS`. The launcher's SSH public key comes from the staged `shared/ssh-key.pub`; operators must provide users with its matching private key separately. See [setup](../getting-started/prerequisites.md) and [environment variables](../reference/environment.md).

Builder Workspace state is coordinated by the **Factory State Authority**, the sole reader and writer of `factory-state-v1`. Dashboard and launch workers call it remotely; the authority runs one container and one state operation at a time. Keep this function's concurrency limit at one. See [ADR 0094](../adr/0094-serialized-factory-state-authority.md).

Before migrating from the earlier independently mounted workers, stop accepting new launches and drain the old web and launch containers. Also drain the authority before deploying a changed authority revision: old and new revisions must not write the state Volume concurrently. Existing records need no conversion.

To verify state coordination against Modal without provisioning a sandbox or touching production state, run `python sandboxes/scripts/test_live_factory_state.py`. It uses an ephemeral App and Volume to check competing workers, ownership, workspace and port uniqueness, and duplicate execution.

Deploy the Modal backend from a clean checkout:

```bash
modal deploy sandboxes/sandbox/function.py
```

For development with local edits:

```bash
ALLOW_DIRTY_DEPLOY=1 modal serve sandboxes/sandbox/function.py
```

The deployed Hosted Sandbox Control Plane receives captured factory configuration (including `RESOURCE_PLANE_SSH_*`, reading `RESOURCE_PLANE_SSH_KEY` into `RESOURCE_PLANE_SSH_PRIVATE_KEY`, `APPS_BASE_DOMAIN`, and `CLOUDFLARE_DNS_API_TOKEN`) plus Git provenance. Edit `.env` and redeploy to update production secrets or staged files; modifying a local checkout does not update an already deployed app. `GET /` directly on the Modal origin returns an authenticated API status page, `GET /api/version` returns provenance, and the Next.js dashboard displays both the Hosted Sandbox Control Plane commit (`CP`) and its own deployed build commit (`UI`) in its header.

## Next.js Dashboard & Custom Base Domain via Caddy

After deploying `sandboxes/sandbox/function.py` to Modal and configuring `RESOURCE_PLANE_SSH_*`, `APPS_BASE_DOMAIN`, and `CLOUDFLARE_DNS_API_TOKEN` (or `CLOUDFLARE_API_TOKEN`) in root `.env`, deploy the Next.js **Sandbox Web Dashboard** (`dashboard/`) and standalone **Dashboard Deployer** (`dashboard-deployer/`) to the VPS:

```bash
# Build and deploy the production Sandbox Web Dashboard to https://<APPS_BASE_DOMAIN>
modal-sandbox infra dashboard

# Build and deploy the standalone Dashboard Deployer to https://deploy.<APPS_BASE_DOMAIN>
modal-sandbox infra deployer
```

- **Production Dashboard (`modal-sandbox infra dashboard`)**: Syncs `dashboard/` to `/opt/sandbox-dashboard`, writes `.env` (`SANDBOX_CONTROL_PLANE_URL`, `WEB_UI_USERNAME`, `WEB_UI_PASSWORD`, `APPS_BASE_DOMAIN`, `DASHBOARD_CONTAINER_NAME=sandbox-dashboard-web`, `DASHBOARD_COMPOSE_PROJECT=sandbox-dashboard`, `NEXT_PUBLIC_DASHBOARD_COMMIT`), builds/starts `sandbox-dashboard-web:3000` on `dbhost-network`, configures `/opt/caddy/conf/sites/apps-wildcard.caddy` so apex browser UI and `/api/*` go to `sandbox-dashboard-web:3000` while `/launch`, `/snapshot`, `/health`, and `/api/codex/profiles` route directly to Modal, and cleans up any legacy `/opt/sandbox-dashboard-staging` stack or route.
- **Dashboard Deployer (`modal-sandbox infra deployer`)**: Syncs `dashboard-deployer/` to `/opt/dashboard-deployer`, builds/starts an independent container (`dashboard-deployer-web:3000`, Compose project `dashboard-deployer`) behind the same `WEB_UI_USERNAME` / `WEB_UI_PASSWORD` Basic Auth middleware, and wires `https://deploy.<APPS_BASE_DOMAIN>` via `/opt/caddy/conf/apps/dashboard-deployer.caddy`. Its **Deploy Sandbox Web Dashboard** button triggers `POST /api/dashboard/deploy` on the Hosted Sandbox Control Plane to clone `main` from `${GH_ORG_NAME}/software-factory` asynchronously, rebuild/deploy `dashboard/` to `https://<APPS_BASE_DOMAIN>` (without redeploying Modal backend functions), and stream live status/logs.

Running `modal-sandbox infra caddy --wildcard` directly configures wildcard DNS-01 TLS and Modal CLI apex routes (`404` for browser paths) until `modal-sandbox infra dashboard` deploys the apex Next.js UI.

## Launch through the dashboard or CLI

The Next.js dashboard provides four App Router views:

- **Builder (`/`)**: Prompt-first Builder Workspace launcher with **Prime Sandbox** reuse partitioned by runtime capabilities (`vm=True`, `memory=1`, `t3=True`, `modal=True`, `sops=True`, and full sandbox-creation options under `Advanced`), manually refreshed **Repository Catalog** picker (`GET /api/github/repos`, `POST /api/github/repos/refresh`), builder model/thought-level selection (`gemini-4-hydrogen` with `Thinking: Extra` default), T3-managed Git worktrees per repo conversation (running `pnpm install` only when `web_app` is enabled), automatic card removal on sandbox termination, live launch progress, and one-click T3 Code redirect (`#token=`).
- **Sandboxes (`/sandboxes`)**: Active sandbox discovery across Modal Apps and Modal Profiles, **Prime** badges, live 24-hour lifespan progress bars, per-sandbox accrued Modal cost estimates (`GET /api/sandboxes/costs`), **T3Code Pairing Links** modal (`GET/POST /api/sandboxes/{sandbox_id}/t3-links`), SSE streaming launch modal (`vm=True`, `memory=1` default), terminate actions, and Filesystem Snapshot capture.
- **Snapshots (`/snapshots`)**: Persistent snapshot registry listing with capture-time apparent **Rootfs Size** (`df`), snapshot resume modal, and registry record deletion.
- **Scratchpad (`/scratchpad`)**: Split **Ideas** (`config/scratchpad/` with AI-assisted refinement) and **Raw** (`config/raw/` verbatim capture) note views backed by the Scratchpad Catalog in `factory-state-v1`, with copy, Builder load, and delete actions.

Builder Workspace, Launch Request, Repository Catalog, and Scratchpad Catalog state is stored in `modal.Volume` (`factory-state-v1`).

Each instance has a generated suffix, such as `dev-box-a1b2c3d4`, even when its Modal App is named `dev-box`. Use the displayed SSH host, port, and generated alias. Dashboard launch does not write to the browser user's local `~/.ssh/config`. The remote CLI can register those details locally:

```bash
modal-sandbox --remote --endpoint-url https://<control-plane-url> \
  --name dev-box --no-cloudflare
```

Set `MODAL_SANDBOX_ENDPOINT_URL` to omit `--endpoint-url`. The remote CLI authenticates with the same `WEB_UI_USERNAME` / `WEB_UI_PASSWORD` as the dashboard.

Cloudflare application ingress requires a configured tunnel token. The enabled flag or displayed hostname alone does not mean that a tunnel was initialized. T3 has its own Modal HTTPS endpoint; see [ingress](../architecture/ingress.md).

## Builder Workspace identity and lifecycle

Each Builder launch creates a Builder Workspace with its own coding conversation. Selecting the same Target Repository twice creates separate Git worktrees and conversations that can share a base checkout, T3 Project, and Prime Sandbox. A Resource Plane Project is a separate grouping of databases and object storage; it is not a T3 Project or a Builder Workspace.

Creating or relaunching a Builder Workspace creates a tracked Launch Request. Opening a running Builder Workspace reconnects to its existing conversation with a fresh pairing token. A relaunch preserves the Builder Workspace identity while replacing its current attachment; once its sandbox is confirmed terminated, the dashboard prunes the workspace record and associated Launch Request history.

Builder Workspaces in a Prime Sandbox share compute resources and sandbox lifetime. Deleting a Builder Workspace through the API cleans up that workspace while preserving the shared Prime Sandbox and sibling workspaces. A Hosted App has its own deployment ownership and lifetime on the VPS; its deployment is independent of Builder Workspace tracking.

A Filesystem Snapshot covers the whole sandbox's root filesystem, including all workspaces sharing it. Resumption starts a new sandbox from the captured files; it does not restore separately stored Builder Workspace tracking records or mounted volume data. See [snapshots](../architecture/snapshots.md) and the [glossary](../reference/glossary.md).

## API routes

The API retains its existing `/api/apps` routes and `app_id` fields for Builder Workspaces. The implementation model is still named `FactoryAppRecord`; its `project_id` identifies the T3 Project. The Resource Plane Management API's `projectId` identifies a Resource Plane Project. These literal identifiers are useful when reading payloads or code.

| Method | Route | Authentication | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Basic | Minimal authenticated HTML API status page on the Modal origin (Next.js UI lives in `dashboard/`) |
| `GET` | `/api/scratchpad/notes` | Basic | Return cached Ideas (`config/scratchpad/`) and Raw (`config/raw/`) lists from `factory-state-v1` |
| `POST` | `/api/scratchpad/notes/refresh` | Basic | Refresh cached Ideas and Raw lists from GitHub |
| `GET` | `/api/scratchpad/notes/{filename}` | Basic | Read an Idea Note or Raw Note (`?section=ideas|raw`), fetching lazily from GitHub on cache miss |
| `POST` | `/api/scratchpad/suggest` | Basic | Refine raw Idea draft into title + Markdown via free OpenCode CLI model |
| `POST` | `/api/scratchpad/notes` | Basic | Commit an Idea Note (`config/scratchpad/<slug>.md`) or verbatim Raw Note (`config/raw/<slug>.md`) |
| `DELETE` | `/api/scratchpad/notes/{filename}` | Basic | Delete an Idea Note or Raw Note (`?section=ideas|raw`) from GitHub and update cache |
| `GET` | `/health` | None | Hosted Sandbox Control Plane liveness |
| `GET` | `/api/version` | Basic | Deployed factory provenance |
| `GET` | `/api/profiles` | Basic | Modal Profiles |
| `GET` | `/api/models` | Basic | Available builder provider/model choices |
| `GET` | `/api/github/repos` | Basic | Return persisted Repository Catalog from `factory-state-v1` |
| `POST` | `/api/github/repos/refresh` | Basic | Manually refresh Repository Catalog from GitHub |
| `GET` | `/api/apps` | Basic | List Builder Workspaces enriched with sandbox state and snapshots |
| `POST` | `/api/apps` | Basic | Create a Builder Workspace and spawn a durable Launch Request |
| `GET` | `/api/apps/{app_id}` | Basic | Get one Builder Workspace enriched with live sandbox state |
| `POST` | `/api/apps/{app_id}/open` | Basic | Reconnect to a running Builder Workspace with a fresh pairing token and T3 chat handoff URL |
| `POST` | `/api/apps/{app_id}/relaunch` | Basic | Spawn a Launch Request (`?resume=true` resumes from failed step when sandbox is alive) |
| `DELETE` | `/api/apps/{app_id}` | Basic | Delete a Builder Workspace and clean up its workspace; preserve shared Prime Sandboxes |
| `GET` | `/api/primes` | Basic | List tracked Prime Sandboxes enriched with runtime status and Builder Workspace counts |
| `GET` | `/api/launches/{request_id}` | Basic | Poll Launch Request progress, logs, and T3 handoff URL |
| `GET` | `/api/sandboxes` | Basic | Active sandbox discovery |
| `POST` | `/api/sandboxes` | Basic | Launch with dashboard payload (`mode`, repo/name, options) |
| `GET` | `/api/sandboxes/costs` | Basic | Query per-sandbox accrued Modal spend with TTL caching |
| `POST` | `/api/sandboxes/stream` | Basic | Launch with SSE progress events (`log`, `done`, or `error`) |
| `POST` | `/api/sandboxes/{sandbox_id}/terminate` | Basic | Terminate an instance |
| `POST` | `/api/sandboxes/{sandbox_id}/snapshot` | Basic | Capture snapshot with name, TTL, timeout, and optional termination |
| `GET` | `/api/sandboxes/{sandbox_id}/t3-links` | Basic | List recorded T3 Code Server **Pairing URLs** and active/used/expired statuses |
| `POST` | `/api/sandboxes/{sandbox_id}/t3-links` | Basic | Generate and persist a new 24h one-time T3 Code Server **Pairing URL** |
| `GET` | `/api/snapshots` | Basic | List snapshot registry records |
| `DELETE` | `/api/snapshots/{image_id}` | Basic | Delete registry record; leaves the underlying image intact |
| `POST` | `/api/snapshots/{image_id}/launch` | Basic | Start a new sandbox from a Filesystem Snapshot with launch options |
| `POST` | `/api/dashboard/deploy` | Basic | Queue async build and deploy of `dashboard/` (`main`) to the App Base Domain |
| `GET` | `/api/dashboard/deploy` | Basic | Return latest dashboard self-deployment record and status |
| `GET` | `/api/dashboard/deploy/{deploy_id}` | Basic | Poll status and logs for one dashboard self-deployment job |
| `POST` | `/launch` | Basic | Launch a sandbox from `core.LaunchRequest` configuration |
| `POST` | `/snapshot` | Basic | Headless snapshot capture |
| `GET` | `/api/codex/profiles` | Scoped bearer credential | Codex Credential Profile pool status |

For headless calls, `/launch` accepts `repo` or standalone `name`, plus the launch fields defined in `sandboxes/sandbox/core.py`. That module's `LaunchRequest` is sandbox launch configuration; the tracked Builder provisioning attempt is represented by `LaunchRequestRecord`. The dashboard `/api/sandboxes` payload adds a `mode` (`repo` or `standalone`) and supports its own subset of launch fields. `/snapshot` takes `sandbox_id`, optional `ttl_days` (30), `timeout` (180 seconds), and `terminate` (false).

The source request models and FastAPI `/openapi.json` schema provide field-level details. The Resource Plane Management API uses its own Admin Token, separate from sandbox dashboard Basic credentials and the scoped Codex status credential.

## Credentials, snapshots, and service lifecycle

The Hosted Sandbox Control Plane reads the factory root `.env`, resolves authentication and provenance, and fills selected missing values from the host environment. Child sandbox propagation has a separate path; it may include factory secrets even for standalone launches. See [resolution rules](../reference/environment.md#resolution-and-propagation).

`modal serve` is tied to the development session. `modal deploy` publishes a persistent app that can scale to zero; launched sandboxes have their own lifecycle. Filesystem snapshots retain files written by startup or tools, including credential files. Review [secrets](../architecture/secrets.md) and [snapshots](../architecture/snapshots.md) before sharing or retaining them.
