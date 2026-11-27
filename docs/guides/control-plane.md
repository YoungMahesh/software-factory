# Hosted Sandbox Control Plane & Dashboard

The sandbox control plane pairs a FastAPI backend and Launch Coordinator hosted on Modal (`sandboxes/sandbox/function.py`) with a modular Next.js 16 + React 19 **Sandbox Web Dashboard** and same-origin BFF proxy (`dashboard/apps/web`) deployed to the VPS at `/opt/sandbox-dashboard`. It launches development sandboxes through the same launcher used by the local CLI and is separate from the Resource Plane persistence console. See [ADR 0096](../adr/0096-nextjs-sandbox-dashboard-and-bff.md).

## Configuration and deployment

Install the factory requirements, authenticate the launch host with Modal, and set both required dashboard credentials in the factory root `.env` or process environment:

```env
WEB_UI_USERNAME=admin
WEB_UI_PASSWORD=replace-with-a-strong-password
```

There is no implicit dashboard username. Missing credentials stop deploy/serve. Repository launches also require `GH_TOKEN`, with `GH_ORG_NAME` for shorthand names. Deployment warns about missing GitHub or Age credentials; `MODAL_ENFORCE_AUTH=1` makes missing GitHub access a deployment error. Standalone launches do not require GitHub access.

Configure provider tokens, `MODAL_TOKENS`, vault decryption, and ingress credentials for the capabilities you intend to expose. `--modal` inside child sandboxes requires valid `MODAL_TOKENS`. The launcher's SSH public key comes from the staged `shared/ssh-key.pub`; operators must provide users with its matching private key separately. See [setup](../getting-started/prerequisites.md) and [environment variables](../reference/environment.md).

Factory App state is coordinated by the **Factory State Authority**, the sole reader and writer of `factory-state-v1`. Dashboard and launch workers call it remotely; the authority runs one container and one state operation at a time. Keep this function's concurrency limit at one. See [ADR 0094](../adr/0094-serialized-factory-state-authority.md).

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

The deployed control plane receives captured factory configuration and Git provenance. Edit `.env` and redeploy to update production secrets or staged files; modifying a local checkout does not update an already deployed app. `GET /` directly on the Modal origin returns an authenticated API status page, `GET /api/version` returns provenance, and the Next.js dashboard displays the deployed commit in its footer/shell.

## Next.js Dashboard & Custom Base Domain via Caddy

After deploying `sandboxes/sandbox/function.py` to Modal and configuring `APPS_BASE_DOMAIN` (plus `CLOUDFLARE_DNS_API_TOKEN` or `CLOUDFLARE_API_TOKEN`) in root `.env`, deploy the Next.js Sandbox Web Dashboard (`dashboard/`) to `/opt/sandbox-dashboard` on the VPS and expose it on `APPS_BASE_DOMAIN`:

```bash
# Stage on a preview subdomain first (e.g. https://dashboard.<APPS_BASE_DOMAIN>)
modal-sandbox infra dashboard --subdomain dashboard

# Cut over the apex (https://<APPS_BASE_DOMAIN>) to Next.js and sync /opt/caddy to Central Config Store
modal-sandbox infra dashboard --cutover --sync
```

`modal-sandbox infra dashboard` transfers `dashboard/` over SSH, writes `/opt/sandbox-dashboard/.env` (`SANDBOX_CONTROL_PLANE_URL`, `WEB_UI_USERNAME`, `WEB_UI_PASSWORD`, `APPS_BASE_DOMAIN`), builds and runs the Docker Compose stack attached to `dbhost-network`, and configures `/opt/caddy/conf/sites/apps-wildcard.caddy` on `--cutover`. In cutover mode, Caddy routes apex browser UI and `/api/*` requests to `sandbox-dashboard-web:3000` (which enforces HTTP Basic Auth in Next.js middleware and forwards `/api/[...path]` to `SANDBOX_CONTROL_PLANE_URL`) while forwarding Modal CLI/status paths (`/launch`, `/snapshot`, `/health`, `/api/codex/profiles`) directly to Modal (`SANDBOX_DASHBOARD_UPSTREAM` or Modal SDK auto-discovery).

Before Next.js cutover, `modal-sandbox infra caddy --wildcard` proxies the apex of `APPS_BASE_DOMAIN` directly to Modal (pass `--no-sync-env` to skip setting empty `MODAL_SANDBOX_ENDPOINT_URL`, or `--no-dashboard` to revert the apex to `404`).

## Launch through the dashboard or CLI

The Next.js dashboard provides four App Router views:

- **Builder (`/`)**: Prompt-first Factory App launcher with **Prime Sandbox** reuse partitioned by runtime capabilities (`vm=True`, `memory=1`, `t3=True`, `modal=True`, `sops=True`, and full sandbox-creation options under `Advanced`), manually refreshed **GitHub Repository Catalog** picker (`GET /api/github/repos`, `POST /api/github/repos/refresh`), builder model/thought-level selection (`gemini-4-hydrogen` with `Thinking: Extra` default), T3-managed Git worktrees per repo conversation (running `pnpm install` only when `web_app` is enabled), automatic card removal on sandbox termination, live launch progress, and one-click T3 Code redirect (`#token=`).
- **Sandboxes (`/sandboxes`)**: Active sandbox discovery across apps/profiles, **Prime** badges, live 24-hour lifespan progress bars, per-sandbox accrued Modal cost estimates (`GET /api/sandboxes/costs`), **T3Code Pairing Links** modal (`GET/POST /api/sandboxes/{sandbox_id}/t3-links`), SSE streaming launch modal (`vm=True`, `memory=1` default), terminate actions, and filesystem snapshot capture.
- **Snapshots (`/snapshots`)**: Persistent snapshot registry listing with capture-time apparent **Rootfs Size** (`df`), snapshot resume modal, and registry record deletion.
- **Scratchpad (`/scratchpad`)**: Split **Ideas** (`config/scratchpad/` with AI-assisted refinement) and **Raw** (`config/raw/` verbatim capture) note views backed by a persisted `factory-state-v1` cache, with copy, Builder load, and delete actions.

Factory App, Launch Request, Repository Catalog Cache, and Scratchpad Catalog Cache state is stored in `modal.Volume` (`factory-state-v1`).

Each instance has a generated suffix, such as `dev-box-a1b2c3d4`, even when its Modal App is named `dev-box`. Use the displayed SSH host, port, and generated alias. Dashboard launch does not write to the browser user's local `~/.ssh/config`. The remote CLI can register those details locally:

```bash
modal-sandbox --remote --endpoint-url https://<control-plane-url> \
  --name dev-box --no-cloudflare
```

Set `MODAL_SANDBOX_ENDPOINT_URL` to omit `--endpoint-url`. The remote CLI authenticates with the same `WEB_UI_USERNAME` / `WEB_UI_PASSWORD` as the dashboard.

Cloudflare application ingress requires a configured tunnel token. The enabled flag or displayed hostname alone does not mean that a tunnel was initialized. T3 has its own Modal HTTPS endpoint; see [ingress](../architecture/ingress.md).

## API routes

| Method | Route | Authentication | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Basic | Minimal authenticated HTML API status page on the Modal origin (Next.js UI lives in `dashboard/`) |
| `GET` | `/api/scratchpad/notes` | Basic | Return cached Ideas (`config/scratchpad/`) and Raw (`config/raw/`) lists from `factory-state-v1` |
| `POST` | `/api/scratchpad/notes/refresh` | Basic | Refresh cached Ideas and Raw lists from GitHub |
| `GET` | `/api/scratchpad/notes/{filename}` | Basic | Read an Idea Note or Raw Note (`?section=ideas|raw`), fetching lazily from GitHub on cache miss |
| `POST` | `/api/scratchpad/suggest` | Basic | Refine raw Idea draft into title + Markdown via free OpenCode CLI model |
| `POST` | `/api/scratchpad/notes` | Basic | Commit an Idea Note (`config/scratchpad/<slug>.md`) or verbatim Raw Note (`config/raw/<slug>.md`) |
| `DELETE` | `/api/scratchpad/notes/{filename}` | Basic | Delete an Idea Note or Raw Note (`?section=ideas|raw`) from GitHub and update cache |
| `GET` | `/health` | None | Control plane liveness |
| `GET` | `/api/version` | Basic | Deployed factory provenance |
| `GET` | `/api/profiles` | Basic | Modal workspace profiles |
| `GET` | `/api/models` | Basic | Available builder provider/model choices |
| `GET` | `/api/github/repos` | Basic | Return persisted GitHub Repository Catalog Cache from `factory-state-v1` |
| `POST` | `/api/github/repos/refresh` | Basic | Manually refresh GitHub Repository Catalog Cache from GitHub |
| `GET` | `/api/apps` | Basic | List Factory Apps enriched with sandbox state and snapshots |
| `POST` | `/api/apps` | Basic | Create a Factory App and spawn a durable Launch Request |
| `GET` | `/api/apps/{app_id}` | Basic | Get one Factory App enriched with live sandbox state |
| `POST` | `/api/apps/{app_id}/open` | Basic | Mint a short-lived pairing token and return direct T3 chat handoff URL |
| `POST` | `/api/apps/{app_id}/relaunch` | Basic | Spawn a Launch Request (`?resume=true` resumes from failed step when sandbox is alive) |
| `DELETE` | `/api/apps/{app_id}` | Basic | Delete a Factory App record and optionally terminate its active sandbox |
| `GET` | `/api/primes` | Basic | List tracked Prime Sandboxes enriched with runtime status and hosted app counts |
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
| `POST` | `/api/snapshots/{image_id}/launch` | Basic | Restore an image with launch options |
| `POST` | `/launch` | Basic | Headless `LaunchRequest` provisioning |
| `POST` | `/snapshot` | Basic | Headless snapshot capture |
| `GET` | `/api/codex/profiles` | Scoped bearer credential | Codex login pool status |

For headless calls, `/launch` accepts `repo` or standalone `name`, plus the launch fields defined in `sandboxes/sandbox/core.py`. The dashboard `/api/sandboxes` payload adds a `mode` (`repo` or `standalone`) and supports its own subset of launch fields. `/snapshot` takes `sandbox_id`, optional `ttl_days` (30), `timeout` (180 seconds), and `terminate` (false).

The source request models and FastAPI `/openapi.json` schema provide field-level details. Do not interchange Resource Plane MCP bearer tokens with sandbox dashboard Basic credentials or the scoped Codex status credential.

## Credentials, snapshots, and service lifecycle

The control plane reads the factory root `.env`, resolves authentication and provenance, and fills selected missing values from the host environment. Child sandbox propagation has a separate path; it may include factory secrets even for standalone launches. See [resolution rules](../reference/environment.md#resolution-and-propagation).

`modal serve` is tied to the development session. `modal deploy` publishes a persistent app that can scale to zero; launched sandboxes have their own lifecycle. Filesystem snapshots retain files written by startup or tools, including credential files. Review [secrets](../architecture/secrets.md) and [snapshots](../architecture/snapshots.md) before sharing or retaining them.
