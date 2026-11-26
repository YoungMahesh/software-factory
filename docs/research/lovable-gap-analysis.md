# Software Factory: gaps toward a Lovable-style workflow

Assessment date: 2026-11-26. Local baseline: `0276323`.

Scope: the user intends to interact with an AI agent in **T3 Code chat**, with the application open beside it in the **T3 Code browser**. T3 is the builder interface. A separate chat/preview product is outside the immediate goal.

This is a source and documentation assessment, not a deployed-service audit. “Present” means reusable implementation exists, not verified production readiness. Priorities are recommendations, not a committed roadmap. The GitHub query returned no open issues at assessment time.

## Immediate question: homepage prompt to T3 web chat

The user's next clarification identifies the entry-point handoff as the main missing feature. Recommended design: a small prompt homepage plus a factory launch job, with T3 serving the ongoing chat and browser experience.

1. The homepage submits the prompt to a proposed factory build endpoint. Save the original prompt and a stable request/job ID before provisioning.
2. The job launches a new T3-enabled sandbox using existing factory provisioning. Prepare a generated application workspace there before starting the agent; alternatively let a bootstrap agent scaffold it under explicit instructions.
3. Wait for T3 readiness, register the intended application directory as a T3 project, and start a thread with the original user prompt. Reuse the existing T3 provider configuration rather than rebuilding an agent runner.
4. Save the association between request, sandbox, workspace/project, environment, and thread. This supports refresh/retry and a subsequent “Open project” action without submitting the prompt twice.
5. Authenticate the browser to that sandbox's T3 web UI using the existing pairing facility, then navigate to the created thread. The thread is already running, so the user sees the first build in progress.
6. The agent runs the app and opens it in the adjacent T3 browser. Further interaction stays inside T3.

Initially checked with the installed `t3 v0.1.11` CLI help and subsequently exercised in the live test described below:

```text
t3 project add [flags] <path>
t3 thread start [flags] <project> <message>
```

`thread start` accepts either a project ID or a path inside the project; `message` may be `-` to read stdin. It supports `--base-dir`, `--provider`, `--model`, `--title`, and `--json`. Run these inside the target sandbox, addressed to its own T3 data directory. Pass untrusted prompt text through stdin rather than interpolating it into a shell command. Do not use `--wait` for the homepage handoff: redirect while the agent works.

Existing factory [launch schemas](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/sandboxes/sandbox/core.py) return `t3_url` and `t3_pair_url`, but have no initial-prompt or T3-thread fields. [T3 setup](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/sandboxes/sandbox/t3.py) provisions pairing; it does not create the application thread. These are the concrete integration seams to extend.

**Browser navigation is now live-verified on T3 v0.1.11.** The installed T3 client accepts a one-time pairing token on the direct chat route: `https://<sandbox-t3-host>/<environmentId>/<encodedThreadId>#token=<one-time-token>`. A fresh incognito browser profile authenticated, removed the fragment, and stayed in the intended chat; reloading the resulting token-free URL also worked. The separate `/pair#token=...` route authenticated but opened a new draft instead. No T3 redirect patch is needed for the tested direct-route flow. See [live verification](t3-handoff-live-verification.md) for commands, evidence, and remaining integration details. Treat the URL form as verified behavior of the tested version and regression-test it on T3 upgrades. Do not put the prompt in the URL or mistake a desktop `t3-thread://` link for a browser HTTP URL.

The live run also establishes that provider/model discovery is required: Antigravity succeeded with `gemini-3.8-flash`, while the old `gemini-3.8-flash-low` identifier was rejected. CLI-created prompt messages appear as **Agent** in the web UI; decide whether that attribution is acceptable before promising exact homepage-user presentation.

For an MVP, keep one application workspace/project in each sandbox. This makes pairing and workspace routing simpler. Public users would still require ownership checks and isolated credentials/history before access, as described below.

## Existing foundation

| Capability | Existing implementation |
| --- | --- |
| Agent interface and development tools | T3 agents, terminal/file/worktree tooling, pairing, browser tooling, and persistence of supported conversation state and usage: [AI tooling](../guides/ai-tooling.md), [T3 integration](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/sandboxes/sandbox/t3.py) |
| Isolated execution | Sandbox launch/discovery/progress, snapshots, restore, and termination: [control-plane guide](../guides/control-plane.md), [sandbox API](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/sandboxes/sandbox/web.py) |
| App scaffolding | Next.js, optional Expo, Drizzle setup, Better Auth overlay, shared theme/types, Git, optional GitHub/resource/vault/sandbox wiring: [scaffolder](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/sandboxes/sandbox/app_scaffolder/_template.py), [cloud wiring](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/sandboxes/sandbox/app_scaffolder/_cloud.py) |
| Persistent resources | PostgreSQL databases/roles, S3 buckets/credentials, SQL/object consoles, provisioning MCP: [Resource Plane README](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/resource-plane/README.md), [MCP tools](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/resource-plane/apps/web/mcp/server.ts) |
| Preview startup convention | Shared `run-app` skill says to run `pnpm run dev` and open localhost in the T3 browser: [skill](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/sandboxes/shared/skills/run-app/SKILL.md) |
| HTTPS publishing | Host-side Docker builds, migrations, readiness checks, wildcard Caddy routing, deployment ownership, ingress recovery: [deployment](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/sandboxes/sandbox/app_deploy/_deploy.py), [application guide](../guides/applications.md) |
| Secrets | Encrypted environment store and worktree propagation: [credential lifecycle](../architecture/secrets.md) |

Lovable's reference flow combines app generation, iteration, preview, code/history, and publishing. See [Lovable introduction](https://docs.lovable.dev/introduction/welcome) and [capability benchmark](lovable-capabilities.md). T3 plus Software Factory can provide a similar personal development workflow without reproducing every commercial platform feature.

## Remaining work for the T3-based workflow

| Priority | Part | Remaining work |
| --- | --- | --- |
| 1 | Reliable idea-to-preview workflow | Give the agent a consistent recipe for selecting `create-app`, provisioning resources, applying schema changes, installing dependencies, starting the app, opening the T3 browser, and reporting success only after a real browser check. Commands already exist; the repeatable orchestration and failure handling need work. |
| 1 | Complete generated backend/auth | Exercise persistent signup/login/logout, protected data access, and upload/download. The Better Auth overlay configures email/password but no database adapter; the sample database schema contains only `items`. Finish persistent auth wiring and its schema/migrations before treating the starter as complete managed auth. |
| 1 | Dependable preview lifecycle | Extend the minimal startup convention to find the correct app/worktree, select/reuse an available port, check readiness, preserve logs, restart a failed server, and reopen the correct preview after reconnect. Reuse T3 browser/preview facilities. |
| 1 | Publishing from the agent workflow | `deploy-app` runs on the deployment host. Add an authenticated job/API/tool bridge so the agent can request publish and read logs/status/URL while deployment SSH credentials remain on the host. Reuse the existing deploy engine. |
| 2 | Safe checkpoints and restore | Associate source commits/checkpoints with meaningful agent changes and published releases; make restore/redeploy explicit. Keep database restore separate. Git/worktrees, T3 history, and filesystem snapshots already exist, but are different forms of persistence. |
| 2 | Consistent application context | Keep repository, current app/worktree, resource identifiers, environment mapping, preview URL, and deployed URL discoverable. Start with a small durable configuration; a separate platform project registry is only needed if existing project/repo state cannot suffice. |
| 3 | Better design iteration | Add reusable templates/components, screenshot/reference context, browser screenshot verification, and optional click-to-edit/style controls. Browser viewing is already covered by T3; direct visual editing is an additional capability. |

Sources: [cloud sequencing](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/sandboxes/sandbox/app_scaffolder/_cloud.py), [starter auth](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/app-template/apps/web/overlay-auth/lib/auth.ts), [starter DB schema](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/app-template/apps/web/overlay-db/db/schema.ts), [preview recipe](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/sandboxes/shared/skills/run-app/SKILL.md), [deployment guide](../guides/applications.md), [deployment engine](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/sandboxes/sandbox/app_deploy/_deploy.py), [history persistence](../guides/ai-tooling.md), and [snapshots](../architecture/snapshots.md). Absence means no integrated factory implementation was found in the inspected surfaces, not that T3 or third-party tools cannot provide it.

## Recommended first milestone

Use T3 to build a small app with authentication and persistent data. From chat: describe the app → scaffold/provision → implement → verify in the adjacent browser → request a change → publish an HTTPS URL → reconnect later → restore an earlier source version.

Verify failed builds, interrupted resource provisioning, preview restart, sandbox replacement, and failed publish as well as the success path. `create-app` cloud operations are sequential rather than transactional, so retries must inspect already-created resources and avoid duplicate/orphan provisioning. See [application guide](../guides/applications.md).

## Needed only if this becomes a public multi-user platform

- Platform accounts, project ownership, invitations/roles, authorization at every service boundary, and isolation of conversations and resources. Existing dashboards use shared Basic auth, MCP uses an administrative token, and the resource project schema has no member/owner model: [middleware](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/resource-plane/apps/web/middleware.ts), [schema](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/resource-plane/apps/web/db/schema.ts), [Resource Plane](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/resource-plane/README.md).
- Scoped runtime/provisioning credentials and sanitized remix/export. Factory credentials can enter development sandboxes and persist in snapshots: [secrets](../architecture/secrets.md).
- Enforceable per-user usage limits, quotas, metering/billing, operational telemetry, and managed backup/restore. T3 usage caches and health endpoints are useful primitives, not a subscription/operations service: [AI tooling](../guides/ai-tooling.md), [Resource Plane operations](https://github.com/sFactory0/software-factory/blob/0276323238d801ca4443f75a79e4a239438d2475/resource-plane/README.md).
- Self-service custom domains, connector catalog/OAuth, shared templates/remix, and a dedicated builder frontend if T3 no longer meets the intended user experience. These are broader product parity rather than prerequisites to this personal workflow.

## Release and security boundaries

Keep deployment SSH keys on the deployment host. Publish should call an authorized server-side job, not hand VPS administration credentials to the agent. See [deployment boundary](../architecture/secrets.md#vps-deployment-boundary).

Current Caddy recovery handles ingress mutations; it does not undo earlier source transfers, builds, or database migrations. Source restore, filesystem snapshot restore, and database recovery must remain separate operations. See [ownership and recovery](../guides/applications.md#ownership-and-recovery).

No completion percentage or delivery estimate is assigned: existing infrastructure, workflow integration, and public-service readiness measure different things.
