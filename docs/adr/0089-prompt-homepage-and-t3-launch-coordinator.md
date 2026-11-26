# Prompt Homepage and Durable T3 Launch Coordinator

**Status**: Accepted (Amends [ADR 0045](0045-sandbox-runner-web-ui-and-snapshot-registry.md), [ADR 0049](0049-launch-fresh-sandboxes-from-web-control-plane.md), [ADR 0064](0064-default-antigravity-text-and-source-control-writer-model-in-t3-code.md), and [ADR 0087](0087-app-template-and-scaffolder-integration.md)).

We extend the Hosted Sandbox Control Plane (`sandboxes/sandbox/`) with a prompt-first builder homepage and durable Launch Coordinator that turns a user prompt into a scaffolded, Git-initialized **Factory App** inside a fresh Modal sandbox and redirects the browser directly into the live **T3 Code Server** conversation (`https://<sandbox-t3-host>/<environmentId>/<encodedThreadId>#token=<one-time-token>`).

## Context

Prior to this design, launching an application workflow required terminal orchestration (`create-app --cloud` or `modal-sandbox`) followed by manual pairing (`/pair#token=...`), which landed on a fresh T3 draft rather than a prompt-started thread. Meanwhile, the Sandbox Web Dashboard (`sandboxes/sandbox/static/index.html`) exposed only operator-focused sandbox and snapshot tables behind synchronous or connection-bound SSE HTTP endpoints (`fastapi_app` timeout of 180 seconds).

Live verification against T3 Code `v0.1.11` ([t3-handoff-live-verification.md](../research/t3-handoff-live-verification.md)) established that attaching a short-lived one-time pairing token as a `#token=` fragment to the direct chat URL authenticates a fresh browser session and lands directly in the target thread without patching T3's client redirect behavior.

## Decisions

1. **Extend Hosted Sandbox Control Plane for Single-User Self-Hosting**:
   - Make `/` in the Sandbox Web Dashboard prompt-first with a **Factory App** list while preserving the existing **Sandboxes** and **Snapshots** views as tabs under HTTP Basic Authentication (`WEB_UI_USERNAME` / `WEB_UI_PASSWORD`).
   - Run **Launch Request** provisioning asynchronously via a spawned Modal background function (`timeout=600`) rather than inside the 180-second ASGI web handler, using URL-tracked polling (`?launch=<request_id>`) so browser refreshes do not re-submit prompts.

2. **Dedicated `modal.Volume` Store (`factory-state-v1`) for App and Launch Records**:
   - Persist `Factory App` and `Launch Request` metadata as per-record JSON files (`apps/<app_id>.json`, `launches/<request_id>.json`) with atomic replace semantics on a dedicated `modal.Volume` (`factory-state-v1`) rather than `modal.Dict` or Resource Plane PostgreSQL.
   - This avoids `modal.Dict`'s 7-day inactivity entry expiration while keeping the Hosted Sandbox Control Plane self-contained when deployed without the Resource Plane.

3. **Phase 1 Git-Only Ephemeral Sandbox Model (No GitHub Required)**:
   - Scaffold **Factory Apps** inside fresh `Standalone Sandbox` containers (`NO_REPO=1`, `no_cloudflare=True`, `vm=False` by default) using local Git via `create-app` (defaulting to the Next.js **App Template**, toggleable to a blank Git workspace or `+ Mobile`), without creating GitHub repositories or pushing to `env-store`, staging the minimal `sandbox` Python runtime alongside `app-template` so in-sandbox `create-app` runs standalone.
   - Auto-provision a Resource Plane PostgreSQL database only when `RESOURCE_PLANE_DOMAIN` and `RESOURCE_PLANE_ADMIN_TOKEN` are configured.
   - Keep Phase 1 sandboxes single-session ephemeral compute: reopening a running app mints a fresh 5-minute pairing token; stopped apps expose **Relaunch from prompt** (and **Resume from Snapshot** when a matching entry exists in the `Snapshot Registry`). Failed partial sandboxes are terminated automatically.

4. **Antigravity `gemini-4-hydrogen` Selection, Prompt Framing, and Attribution**:
   - Dynamically resolve an authenticated Antigravity `instanceId` and pass the advertised model slug `gemini-4-hydrogen` (with optional `thought_level` option) to `t3 thread start`, keeping `gemini-4-hydrogen-low` scoped to `sourceControlWriterModelSelection` / `textGenerationModelSelection` per [ADR 0064](0064-default-antigravity-text-and-source-control-writer-model-in-t3-code.md).
   - Store the raw user prompt on the `Factory App` record and append the one-time `run-app` instruction (start `pnpm run dev` / local server and open localhost in T3's browser) only to the stdin payload sent to `t3 thread start`, keeping template `AGENTS.md` clean.
   - Accept T3 `v0.1.11`'s stock `Agent` message badge on CLI-created initial prompts rather than maintaining binary SEA patches or reverse-engineering internal WebSocket RPC auth.

## Considered Options

- **Build Homepage and Coordinator in Resource Plane (`resource-plane/`)**: Rejected for Phase 1 because Modal credentials, `SandboxLauncher`, `app-template` staging, and `WEB_UI_*` auth already live in `sandboxes/sandbox/function.py`.
- **Store `Factory App` Metadata in `modal.Dict`**: Rejected because `modal.Dict` entries expire after 7 days of inactivity, which would drop inactive app records.
- **Automatic Volume Mirroring for No-GitHub Workspaces**: Deferred past Phase 1 in favor of explicit **Snapshot** / **Relaunch from prompt** controls to minimize Phase 1 moving parts.
- **Place `run-app` Instruction in Template `AGENTS.md`**: Rejected because preview startup after initial build is a one-time prompt instruction rather than a permanent repository rule.

## Consequences

- Self-hosted single-user deployments can go from prompt to live T3 coding session and side-by-side preview without GitHub or VPS setup.
- **Factory App** code lives ephemerally inside its sandbox unless manually snapshotted via the `Snapshot Registry` (up to Modal's 4h idle / 22h max lifetime).
- All new Python coordinator, store, and router modules under `sandboxes/sandbox/` obey the universal `<= 500`-line file budget.
