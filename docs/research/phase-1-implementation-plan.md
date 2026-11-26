# Phase 1 Implementation Plan: Prompt Homepage → Launch Coordinator → T3 Web Chat

Plan date: 2026-11-26. Baseline commit: `7e780ca`.
Governing ADR: [ADR 0089](../adr/0089-prompt-homepage-and-t3-launch-coordinator.md).
Prior evidence: [lovable-gap-analysis.md](lovable-gap-analysis.md), [t3-handoff-live-verification.md](t3-handoff-live-verification.md).

## 1. Scope & Settled Design Decisions

This plan covers **Phase 1 only**: turning a prompt on the **Hosted Sandbox Control Plane** homepage into a ready **Factory App** inside a Modal sandbox and redirecting directly into its **T3 Code Server** chat (`https://<sandbox-t3-host>/<environmentId>/<encodedThreadId>#token=<one-time-token>`).

Settled constraints from design review:
- **Single-user self-hosted**: Authenticated via existing `WEB_UI_USERNAME` / `WEB_UI_PASSWORD` HTTP Basic auth (`check_authentication` in [`sandboxes/sandbox/web.py`](https://github.com/sFactory0/software-factory/blob/7e780ca8ed50493240a8a43161c69285ec9c9037/sandboxes/sandbox/web.py)).
- **Git only, no GitHub**: Local Git repositories initialized inside the sandbox via `App Scaffolder` (`create-app`) or `Standalone Sandbox` bootstrap (`NO_REPO=1`), with no `--github` or `--push-vault`.
- **Optional Resource Plane DB**: Auto-provision a Resource Plane PostgreSQL database only when `RESOURCE_PLANE_DOMAIN` and `RESOURCE_PLANE_ADMIN_TOKEN` are configured.
- **Ephemeral single-session sandboxes + manual snapshots**: Reopen running sandboxes via fresh pairing token; stopped apps show **Relaunch from prompt** and (if a `Filesystem Snapshot` exists in `Snapshot Registry`) **Resume from Snapshot**.
- **Prompt framing & attribution**: Store the raw prompt on the **Factory App** record; append the one-time `run-app` instruction only to the message passed via stdin to `t3 thread start`; accept T3's `Agent` badge on CLI-created prompts for v1.
- **Default AI model**: Dynamically resolve an authenticated Antigravity `instanceId` and pass `--model gemini-4-hydrogen` (with optional `thought_level`), verified live via `Sandbox Live Verification`.

## 2. Architecture & Request Lifecycle

```text
Browser (/)
  │  POST /api/apps { prompt, name?, template, mobile, model_selection, vm?, profile? }
  ▼
FastAPI Router (apps/routes.py)
  │  1. Save FactoryAppRecord + LaunchRequestRecord (status=queued) to Volume `factory-state-v1`
  │  2. volume.commit()
  │  3. run_launch_request.spawn(request_id)
  │  4. Return 202 { app_id, request_id }
  ▼
Modal Worker Function (function.py -> apps/coordinator.py, timeout=600)
  ├─ Step 1 (launching_sandbox): SandboxLauncher.run(Standalone, t3=True, no_cloudflare=True, ...)
  ├─ Step 2 (scaffolding_workspace):
  │    - If template == "nextjs": run `create-app /root/<slug> -y [--mobile-app]` in /root/<slug>
  │    - If Resource Plane configured and template == "nextjs": create DB & write DATABASE_URL to .env (+ .git/env-vault/)
  ├─ Step 3 (waiting_t3): poll `/root/.t3/userdata/server-runtime.json`, `environment-id`, and provider cache (`antigravity*.json`)
  ├─ Step 4 (starting_thread):
  │    - `t3 project add --base-dir /root/.t3 --title <title> /root/<slug>`
  │    - Idempotency probe: `t3 thread list --project /root/<slug> --base-dir /root/.t3 --json`
  │    - `t3 thread start ... /root/<slug> -` (stdin = raw_prompt + one-time run-app suffix)
  ├─ Step 5 (ready):
  │    - `t3 auth pairing create --base-dir /root/.t3 --ttl 5m --json`
  │    - Save sandbox_id, environment_id, project_id, thread_id, t3_url, chat_url on FactoryAppRecord
  │    - Update LaunchRequestRecord status=ready + handoff_url
  └─ On any error: terminate partial sandbox, save error on LaunchRequestRecord & FactoryAppRecord (status=failed)
```

Browser polling (`GET /api/launches/{request_id}` every ~1.5s, tracked in `?launch=<request_id>` across reloads) updates step progress and automatically navigates to `handoff_url` once `status == "ready"`, with a clickable **Open in T3** fallback button.

## 3. Module Breakdown (`<= 500` Physical Lines per `.py` File)

To keep [`sandboxes/sandbox/web.py`](https://github.com/sFactory0/software-factory/blob/7e780ca8ed50493240a8a43161c69285ec9c9037/sandboxes/sandbox/web.py) (currently 451 lines) and all test suites comfortably under the 500-line Universal File Line Budget enforced by [`test_standards.py`](https://github.com/sFactory0/software-factory/blob/7e780ca8ed50493240a8a43161c69285ec9c9037/sandboxes/tests/test_standards.py), decompose new Python code into a cohesive `sandboxes/sandbox/apps/` package:

| File | Responsibility | Target Lines |
| --- | --- | --- |
| `sandboxes/sandbox/apps/__init__.py` | Public exports (`router`, `run_launch_request_job`, domain models) | ~30 |
| `sandboxes/sandbox/apps/models.py` | Pydantic models (`CreateAppPayload`, `FactoryAppRecord`, `LaunchRequestRecord`, `LaunchStatusResponse`, `OpenAppResponse`, `ModelChoice`), prompt-to-slug derivation, and one-time `run-app` prompt suffix builder | ~180 |
| `sandboxes/sandbox/apps/store.py` | `FactoryStateStore` backed by `modal.Volume.from_name("factory-state-v1", create_if_missing=True)` mounted at `/root/.factory-state` (per-record JSON files `apps/<id>.json` and `launches/<id>.json`, `threading.Lock`, `reload()`/`commit()`, atomic `os.replace`, plus explicit local-directory fallback for unit tests and CLI smoke use) | ~220 |
| `sandboxes/sandbox/apps/coordinator.py` | Launch Coordinator: `execute_launch_request`, `open_factory_app`, `relaunch_factory_app`, `delete_factory_app`, in-sandbox T3 readiness + provider/model discovery (`gemini-4-hydrogen` / `thought_level` / fallback selection), idempotent `t3` CLI wrappers (`stdin` write/EOF/drain), optional Resource Plane DB injection, partial-sandbox termination on failure, and `Snapshot Registry` lookup | ~380 |
| `sandboxes/sandbox/apps/routes.py` | Authenticated FastAPI `APIRouter` (`Depends(check_authentication)`) + injectable spawn seam (`set_launch_dispatcher` / default Modal `.spawn()`) | ~220 |
| `sandboxes/sandbox/web.py` | Mount `apps_router` onto `router` / `create_app()` (+~4 lines; remains ~455 lines) | ~455 |
| `sandboxes/sandbox/function.py` | Mount `factory-state-v1` onto `fastapi_app` and add `@app.function(..., volumes={...}, timeout=600)` `run_launch_request(request_id)` | ~285 |
| `sandboxes/sandbox/static/index.html` + `sandboxes/sandbox/static/builder.js` | Prompt-first `/` builder homepage + `Factory Apps` cards + `?launch=` progress view, while keeping existing `Sandboxes` and `Snapshots` tabs and modals intact (preserving existing assertions in [`test_web_fresh_launch.py`](https://github.com/sFactory0/software-factory/blob/7e780ca8ed50493240a8a43161c69285ec9c9037/sandboxes/tests/test_sandbox/test_web_fresh_launch.py)) | HTML/JS |

## 4. Detailed API & Data Contracts

### Data Models (`apps/models.py`)

- **`FactoryAppRecord`**:
  - `app_id: str` (short UUID/ulid, e.g. `app_<hex12>`), `slug: str` (unique sanitized `/root/<slug>` name, disambiguated with short suffix on collision), `title: str`
  - `prompt: str` (raw user prompt), `template: Literal["nextjs", "blank"]`, `mobile_app: bool`, `vm: bool`, `profile: str | None`
  - `provider_instance_id: str | None`, `model: str`, `thought_level: str | None`
  - `owner: str = "operator"` (single-user placeholder field)
  - `status: Literal["provisioning", "ready", "failed"]` (runtime status `running` / `stopped` computed live against Modal sandbox status on read)
  - `latest_request_id: str | None`, `sandbox_id: str | None`, `sandbox_name: str | None`, `environment_id: str | None`, `project_id: str | None`, `thread_id: str | None`, `t3_url: str | None`, `chat_url: str | None`, `database_name: str | None`, `last_error: str | None`
  - `created_at: str`, `updated_at: str`
- **`LaunchRequestRecord`**:
  - `request_id: str` (`req_<hex12>`), `app_id: str`, `kind: Literal["create", "relaunch"]`
  - `status: Literal["queued", "launching_sandbox", "scaffolding_workspace", "waiting_t3", "starting_thread", "ready", "failed"]`
  - `steps: list[dict[str, Any]]`, `logs: list[str]` (tail-bounded)
  - `handoff_url: str | None` (stored transiently or minted on `ready`—never leaked after completion if expired; `/open` always mints a fresh 5m token)
  - `error: str | None`, `created_at: str`, `updated_at: str`

### REST Endpoints (`apps/routes.py`)

All routes share `check_authentication` (HTTP Basic auth):
- `GET /api/models`: Returns curated/default builder model choices (default `Antigravity · Gemini 4 Hydrogen` (`model="gemini-4-hydrogen"`, `thought_level="high"`/`"xhigh"`), plus `Gemini 3.8 Flash`, `Claude Sonnet 4.6`, and optional `OpenCode` / `Codex` choices derived from configured Control Plane environment hints).
- `GET /api/apps`: Lists `FactoryAppRecord` entries sorted newest-first, enriched with live sandbox state (`running` / `stopped` via `modal.Sandbox.from_id(...).poll()`, batch-safe with graceful error handling) and matching `Snapshot Registry` entries (`snapshots.list_snapshots()` filtered by `sandbox_id`).
- `POST /api/apps`: Validates `CreateAppPayload`, creates `FactoryAppRecord` + `LaunchRequestRecord(status="queued")`, commits Volume, dispatches `run_launch_request.spawn(request_id)`, and returns `202` `{ app_id, request_id, status_url }`.
- `GET /api/launches/{request_id}`: Reloads Volume, reads `LaunchRequestRecord` + owning `FactoryAppRecord` summary, returns live status, progress step label, logs, and `handoff_url` when `ready`.
- `POST /api/apps/{app_id}/open`: Checks live sandbox state. If running, mints a fresh 5-minute pairing token (`t3 auth pairing create --base-dir /root/.t3 --ttl 5m --json`) and returns `{ handoff_url, chat_url }`; if stopped, returns `409` with `{ detail, snapshot_image_id? }` so UI offers **Relaunch from prompt** or **Resume from Snapshot**.
- `POST /api/apps/{app_id}/relaunch`: Creates a new `LaunchRequestRecord(kind="relaunch")` from the stored `FactoryAppRecord.prompt` and options, spawns `run_launch_request.spawn(request_id)`, and returns `202`.
- `DELETE /api/apps/{app_id}?terminate_sandbox=true|false`: Optionally terminates the active sandbox via `terminate_sandbox()` and deletes the `FactoryAppRecord` JSON from `factory-state-v1`.

## 5. Crucial Integration Seams & Edge Cases

1. **Modal Volume Sync Discipline**:
   - In [`Volume.md`](https://modal.com/docs/reference/modal.Volume), readers do not see remote writes until `volume.reload()`, and writers must call `volume.commit()`.
   - Wrap every store operation in a module-level `threading.Lock`, ensure no file descriptors stay open across `reload()` / `commit()`, commit before calling `.spawn(request_id)`, and reload before reading in `GET /api/launches/{request_id}` and inside `run_launch_request`.
2. **In-Sandbox Workspace Scaffolding (`create-app` without GitHub)**:
   - Launch `Standalone Sandbox` (`repo=None`, `name=slug`, `t3=True`, `no_cloudflare=True`, `react_native=payload.mobile_app`, `vm=payload.vm`, `profile=payload.profile`).
   - [`startup.sh`](https://github.com/sFactory0/software-factory/blob/7e780ca8ed50493240a8a43161c69285ec9c9037/sandboxes/shared/startup.sh) initializes `/root/<slug>` with `.git` and `.gitignore` and starts `t3 serve` on port `3775`.
   - For `template == "nextjs"`: execute `create-app /root/<slug> -y [--mobile-app]` inside the sandbox (using [`_template.py`](https://github.com/sFactory0/software-factory/blob/7e780ca8ed50493240a8a43161c69285ec9c9037/sandboxes/sandbox/app_scaffolder/_template.py)'s `_STANDALONE_ALLOWED_ENTRIES` support to merge `.gitignore` and reuse `.git` cleanly).
   - If `RESOURCE_PLANE_DOMAIN` and `RESOURCE_PLANE_ADMIN_TOKEN` are present in the Control Plane environment, call `create_database_connection` on the Control Plane side and inject `DATABASE_URL` into `/root/<slug>/.env` (and `.git/env-vault/default.env` + `env.map` so git worktrees inherit it).
3. **Antigravity `gemini-4-hydrogen` Discovery & `t3 thread start`**:
   - Wait for `/root/.t3/userdata/server-runtime.json` and `/root/.t3/userdata/environment-id` inside the sandbox.
   - Read `/root/.t3/userdata/settings.json` and `/root/.t3/caches/<instanceId>.json` to find an enabled, authenticated Antigravity instance (preferring `antigravity`, `antigravity-anv`, `antigravity-mgh`) and verify `gemini-4-hydrogen` (or fallback `gemini-3.8-flash`) appears in `models`.
   - Pass `--provider <instanceId> --model <slug>` and (when chosen) `--option thought_level=<level>` to `t3 thread start /root/<slug> - --base-dir /root/.t3 ... --json`, writing `prompt + "\n\n" + one_time_run_app_instruction` to stdin followed by `write_eof()` and `drain()`.
   - Before retrying an uncertain/timed-out `t3 thread start`, call `t3 thread list --project /root/<slug> --base-dir /root/.t3 --json` so duplicate starter runs are never created.
4. **Homepage Preservation**:
   - Preserve existing **Sandboxes** and **Snapshots** tabs, `#fresh-launch-log-box`, `/api/sandboxes/stream`, and `"software-factory"` / `"SOPS"` text in [`index.html`](https://github.com/sFactory0/software-factory/blob/7e780ca8ed50493240a8a43161c69285ec9c9037/sandboxes/sandbox/static/index.html) so existing dashboard functionality and tests remain unbroken.

## 6. Verification Plan

1. **Automated Unit & Contract Tests (`sandboxes/tests/test_apps/`, `< 500` lines per file)**:
   - `test_models.py`: slug generation/disambiguation, payload validation, one-time prompt suffix isolation.
   - `test_store.py`: per-record atomic JSON CRUD, `reload()`/`commit()` call ordering under mocked `modal.Volume`, concurrent updates across distinct keys.
   - `test_coordinator.py`: full mocked provisioning flow (`SandboxLauncher`, `sb.exec` for `create-app`, T3 file polling, `t3 project add`, `t3 thread list`/`start`, `t3 auth pairing create`), optional Resource Plane DB wiring vs omission, idempotent retry after uncertain `thread start`, automatic partial-sandbox termination on failure, `open_factory_app` fresh token & stopped-sandbox 409, snapshot matching, and delete cleanup.
   - `test_routes.py`: FastAPI `TestClient` with Basic auth covering `POST /api/apps`, `GET /api/launches/{id}`, `GET /api/apps`, `POST /api/apps/{id}/open`, `POST /api/apps/{id}/relaunch`, `DELETE /api/apps/{id}`, and `GET /api/models`.
2. **Repository Standards & Docs Gate**:
   - Run full `pytest` across `sandboxes/tests/` (verifying [`test_standards.py`](https://github.com/sFactory0/software-factory/blob/7e780ca8ed50493240a8a43161c69285ec9c9037/sandboxes/tests/test_standards.py), [`test_docs.py`](https://github.com/sFactory0/software-factory/blob/7e780ca8ed50493240a8a43161c69285ec9c9037/sandboxes/tests/test_docs.py), [`test_documentation_contracts.py`](https://github.com/sFactory0/software-factory/blob/7e780ca8ed50493240a8a43161c69285ec9c9037/sandboxes/tests/test_documentation_contracts.py), and [`test_web_fresh_launch.py`](https://github.com/sFactory0/software-factory/blob/7e780ca8ed50493240a8a43161c69285ec9c9037/sandboxes/tests/test_sandbox/test_web_fresh_launch.py)).
3. **Sandbox Live Verification (`gemini-4-hydrogen` + Browser Handoff)**:
   - Provision an ephemeral `--testing` sandbox (`--no-t3-persist --no-cloudflare --no-ssh-config`), execute the real coordinator sequence (`Standalone Sandbox` + `create-app` + `t3 project add` + `t3 thread start --provider <instance> --model gemini-4-hydrogen` with one-time `run-app` suffix + `t3 auth pairing create --ttl 5m`), verify the resulting app and direct `#token=` chat navigation in a fresh browser session, and terminate the sandbox immediately afterward (`poll()` exit code `137`).
