# Prime Sandbox Reuse for Multi-App Dashboard Prompts

**Status**: Accepted (Amends [ADR 0089](0089-prompt-homepage-and-t3-launch-coordinator.md)).

We evolve the Hosted Sandbox Control Plane (`sandboxes/sandbox/apps/`) from launching a fresh Modal sandbox per prompt to lazily provisioning and reusing a shared, multi-tenant **Prime Sandbox** per capability tuple `(profile, vm, mobile_app)`, creating isolated Factory App workspaces and T3 Code Server threads inside the active container.

## Context

Under [ADR 0089](0089-prompt-homepage-and-t3-launch-coordinator.md), every prompt submitted from the Sandbox Web Dashboard homepage created a dedicated `Standalone Sandbox`, incurring full Modal container provisioning and `t3 serve` startup latency on every request. For rapid multi-prompt prototyping, waiting 60–120 seconds per prompt creates substantial friction, even though a single running `T3 Code Server` supports registering multiple projects (`t3 project add`) and threads (`t3 thread start`) concurrently.

## Decisions

1. **Lazy Multi-App Prime Sandbox Partitioned by `(profile, vm, mobile_app)`**:
   - Track one active **Prime Sandbox** record (`primes/<prime_key>.json` in `factory-state-v1`) per compatibility key `(profile, vm, mobile_app)` because Modal locks workspace credentials, runtime (`gvisor` vs `vm`), volumes (Gradle), and tunnels at container creation time.
   - The first matching prompt lazily provisions the Prime Sandbox (named `prime-sandbox*`) and marks it `ready` once T3 Code Server passes readiness checks. Subsequent matching prompts bypass container launch and T3 boot, attaching directly to the active container with **no automatic app-count cap** until Modal's lifetime/idle limit or manual termination in the **Sandboxes** tab.

2. **Persisted Cold-Start Coordination**:
   - Concurrent prompts arriving before a Prime Sandbox finishes booting coordinate via the persisted `PrimeSandboxRecord` provisioning claim (`owner_request_id`) on `factory-state-v1`. Waiting requests poll and attach once the owner marks the container `ready`, taking over only if the owner fails or its claim becomes stale.

3. **Per-App Workspace and Dev Port Isolation (`3001+`)**:
   - Each prompt scaffolds an independent Git workspace at `/root/<app-slug>` and registers its own T3 Project and T3 Thread.
   - Because sandbox shells export `PORT=3000` in `~/.bashrc`, the coordinator atomically allocates a monotonically increasing `dev_port` starting at `3001` per Prime Sandbox, patches Next.js `apps/web/package.json` (`next dev -p <dev_port>`) and `.env` (`PORT=<dev_port>`), and instructs the agent via the initial `run-app` prompt to preview `http://localhost:<dev_port>`.

4. **Shared Blast Radius with Non-Terminating App Delete & Relaunch**:
   - Co-located Factory Apps share their Prime Sandbox container lifecycle: when the container stops or expires, all apps hosted on it transition to `stopped` and can be relaunched onto an active compatible Prime Sandbox.
   - App-level **Delete** cleans up only that app's metadata, running dev server processes, T3 project/threads (`t3 project remove --force`), and `/root/<slug>` directory without terminating the shared Prime Sandbox. Container-wide termination stays explicit on the **Sandboxes** tab, and **Snapshot** / **Resume Snapshot** remain whole-sandbox operations producing standalone recovery containers.

## Considered Options

- **Pre-warmed Pool of Single-App Idle Sandboxes**: Rejected to avoid idle container compute billing when no prompts are submitted and to allow sharing a single T3 Code Server and Codex Credential Profile across prompts.
- **Automatic Rotation Cap (e.g., 5 Apps per Prime Sandbox) + Homepage Reset Control**: Rejected by user decision in favor of unbounded reuse within Modal's container lifetime and explicit termination via the **Sandboxes** tab.

## Consequences

- Subsequent prompts from the Sandbox Web Dashboard land in a live T3 Code thread in seconds (only workspace scaffolding + `t3 thread start`).
- Sibling apps inside a Prime Sandbox share container CPU/RAM (`4 vCPU / 16 GiB`) and container lifetime; crashing or terminating that Prime Sandbox affects all hosted apps simultaneously.
- All new and modified Python modules in `sandboxes/sandbox/apps/` remain within the `<= 500`-line file budget.
