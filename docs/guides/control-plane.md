# Hosted Sandbox Control Plane

The sandbox control plane is a FastAPI dashboard and REST API hosted on Modal by `sandboxes/sandbox/function.py`. It launches development sandboxes through the same launcher used by the local CLI. It is separate from the Resource Plane persistence console.

## Configuration and deployment

Install the factory requirements, authenticate the launch host with Modal, and set both required dashboard credentials in the factory root `.env` or process environment:

```env
WEB_UI_USERNAME=admin
WEB_UI_PASSWORD=replace-with-a-strong-password
```

There is no implicit dashboard username. Missing credentials stop deploy/serve. Repository launches also require `GH_TOKEN`, with `GH_ORG_NAME` for shorthand names. Deployment warns about missing GitHub or Age credentials; `MODAL_ENFORCE_AUTH=1` makes missing GitHub access a deployment error. Standalone launches do not require GitHub access.

Configure provider tokens, `MODAL_TOKENS`, vault decryption, and ingress credentials for the capabilities you intend to expose. `--modal` inside child sandboxes requires valid `MODAL_TOKENS`. The launcher's SSH public key comes from the staged `shared/ssh-key.pub`; operators must provide users with its matching private key separately. See [setup](../getting-started/prerequisites.md) and [environment variables](../reference/environment.md).

Deploy from a clean checkout:

```bash
modal deploy sandboxes/sandbox/function.py
```

For development with local edits:

```bash
ALLOW_DIRTY_DEPLOY=1 modal serve sandboxes/sandbox/function.py
```

The deployed control plane receives captured factory configuration and Git provenance. Edit `.env` and redeploy to update production secrets or staged files; modifying a local checkout does not update an already deployed app. The dashboard shows the deployed commit, and `GET /api/version` returns provenance.

## Custom base domain via Caddy

After deploying `sandboxes/sandbox/function.py` to Modal and configuring `APPS_BASE_DOMAIN` (plus `CLOUDFLARE_DNS_API_TOKEN` or `CLOUDFLARE_API_TOKEN`) in root `.env`, expose the Sandbox Web Dashboard at `https://<APPS_BASE_DOMAIN>` via the VPS Host Ingress Proxy:

```bash
modal-sandbox infra caddy --wildcard
```

This discovers the deployed `sandbox-control-plane` web URL via Modal SDK (overridable via `SANDBOX_DASHBOARD_UPSTREAM` or `--dashboard-upstream`), proxies the apex of `APPS_BASE_DOMAIN` to Modal inside `/opt/caddy/conf/sites/apps-wildcard.caddy` with `Host` header rewriting and unbuffered SSE streaming, and sets empty `MODAL_SANDBOX_ENDPOINT_URL` in root `.env` to `https://<APPS_BASE_DOMAIN>` (preserving existing values; pass `--no-sync-env` to skip or `--no-dashboard` to revert the apex to `404`). Authentication stays in Modal (`WEB_UI_USERNAME` / `WEB_UI_PASSWORD`).

## Launch through the dashboard or CLI

The dashboard defaults to the prompt-first **Builder** homepage for launching and reopening **Factory Apps** in **T3 Code**, alongside **Sandboxes** and **Snapshots** tabs for inspecting running instances across apps/profiles, terminating instances, capturing filesystem snapshots, and resuming snapshots. Factory App and Launch Request state is stored in `modal.Volume` (`factory-state-v1`).

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
| `GET` | `/` | Basic | Dashboard (Builder homepage, Sandboxes, Snapshots) |
| `GET` | `/health` | None | Control plane liveness |
| `GET` | `/api/version` | Basic | Deployed factory provenance |
| `GET` | `/api/profiles` | Basic | Modal workspace profiles |
| `GET` | `/api/models` | Basic | Available builder provider/model choices |
| `GET` | `/api/apps` | Basic | List Factory Apps enriched with sandbox state and snapshots |
| `POST` | `/api/apps` | Basic | Create a Factory App and spawn a durable Launch Request |
| `GET` | `/api/apps/{app_id}` | Basic | Get one Factory App enriched with live sandbox state |
| `POST` | `/api/apps/{app_id}/open` | Basic | Mint a short-lived pairing token and return direct T3 chat handoff URL |
| `POST` | `/api/apps/{app_id}/relaunch` | Basic | Spawn a Launch Request (`?resume=true` resumes from failed step when sandbox is alive) |
| `DELETE` | `/api/apps/{app_id}` | Basic | Delete a Factory App record and optionally terminate its active sandbox |
| `GET` | `/api/launches/{request_id}` | Basic | Poll Launch Request progress, logs, and T3 handoff URL |
| `GET` | `/api/sandboxes` | Basic | Active sandbox discovery |
| `POST` | `/api/sandboxes` | Basic | Launch with dashboard payload (`mode`, repo/name, options) |
| `POST` | `/api/sandboxes/stream` | Basic | Launch with SSE progress events (`log`, `done`, or `error`) |
| `POST` | `/api/sandboxes/{id}/terminate` | Basic | Terminate an instance |
| `POST` | `/api/sandboxes/{id}/snapshot` | Basic | Capture snapshot with name, TTL, timeout, and optional termination |
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
