# Spec: Dev Server Host Allowlist for Modal Application Tunnels

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

When developers select an application in Factory Studio and launch an interactive preview, the Dedicated Preview Sandbox provisions successfully and launches the development server on port 3000. However, when the live preview workspace embeds the generated Modal Application Tunnel URL (`https://<sandbox-id>-3000.modal.host`), the embedded iframe displays a host rejection error:

```text
Blocked request. This host ("ta-...-3000-...w.modal.host") is not allowed.
To allow this host, add "ta-...-3000-...w.modal.host" to server.allowedHosts in vite.config.js.
```

Modern frontend build tools and dev servers (specifically Vite versions 5.4.12+ and 6/7/8; `calculator-app` runs Vite 8) enforce strict HTTP Host header validation to guard against DNS rebinding attacks. Because Modal Application Tunnels generate dynamic, unique subdomains under `.modal.host` that are not pre-configured in project repositories, the dev server blocks all incoming preview requests. This prevents developers from previewing `calculator-app` or any other Vite-based frontend project in Factory Studio.

## Solution

Implement a defense-in-depth host authorization architecture across the software factory preview infrastructure:

1. **Sandbox Runtime Injection**: Wire the `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` environment variable set to `.modal.host,3000.mahesh0.dev` into preview sandbox execution environments. This immediately enables all current, past, and external repositories (including `calculator-app`) to accept tunnel traffic without requiring repository modifications.
2. **Canonical Template & Repository Alignment**: Update the canonical template repository (`tanstack-start-template`) and active test projects (`calculator-app`) to explicitly declare `server: { allowedHosts: ['.modal.host', '3000.mahesh0.dev'] }` in their configuration, making host authorization an explicit, self-documenting code standard.
3. **Operational Cleanliness**: Refactor preview sandbox termination in the server registry to use non-blocking asynchronous calls (`await sandbox.terminate.aio()`), eliminating runtime usage warnings in server logs.
4. **Architecture Decision Record**: Amend ADR 0037 to document bundler host validation constraints and the scoped wildcard allowlist policy.

## User Stories

1. As a developer launching an application preview in Factory Studio, I want the live preview iframe to display my running web application instead of a "Blocked request" host rejection error, so that I can immediately interact with the application.
2. As a developer previewing an existing repository (such as `calculator-app`), I want the preview sandbox to automatically permit requests originating from the Modal Application Tunnel without requiring manual code changes, so that existing projects work out of the box.
3. As a developer testing multiple applications concurrently, I want each uniquely generated Modal Application Tunnel URL (`https://<sandbox-id>-3000.modal.host`) to be accepted by the dev server, so that dynamic container subdomains are seamlessly supported.
4. As a security-conscious engineer, I want the host allowlist to be scoped specifically to `.modal.host` and `3000.mahesh0.dev` rather than disabling host checks completely, so that the dev server remains safeguarded against unrestricted DNS rebinding attacks.
5. As a developer running an application preview post-assembly line via the `--dev` flag, I want the dev keep-alive daemon to accept tunnel requests identically to dedicated preview sandboxes, so that dev mode behavior is consistent across execution paths.
6. As a developer generating a new frontend project from the canonical template (`tanstack-start-template`), I want the scaffolded project to explicitly declare the tunnel host allowlist in its configuration, so that development server behavior is self-documenting.
7. As an operator stopping an active preview from Factory Studio, I want sandbox termination to execute cleanly without async blocking warnings in server logs, so that operational observability remains uncluttered.
8. As a developer reviewing architectural documentation, I want ADR 0037 to document the host header validation constraints of Modal Application Tunnels, so that the rationale for the wildcard allowlist is clearly understood.
9. As an engineer writing tests for the spawner, I want automated verification that preview sandbox environments receive the tunnel host allowlist variables, so that regressions are caught before container launch.
10. As a developer switching between different repositories in Factory Studio, I want every newly spawned preview container to inherit the host allowlist configuration reliably, so that preview transitions are seamless.
11. As a contributor inspecting sandbox container startup scripts, I want the dev keep-alive daemon block to define fallback defaults for the host allowlist environment variable, so that manual or detached script execution behaves predictably.
12. As a developer previewing an application that uses Cloudflare Ingress, I want the ingress domain (`3000.mahesh0.dev`) included in the allowlist alongside Modal tunnel domains, so that previewing over either tunnel mechanism functions without disruption.

## Implementation Decisions

- **Defense-in-Depth Host Authorization Strategy**:
  Host authorization is applied at two independent tiers: platform-level runtime injection into the container environment and codebase-level configuration in canonical repository templates. This ensures existing un-patched repositories work immediately while new projects adhere to explicit configuration standards.

- **Scoped Wildcard Allowlist (`.modal.host,3000.mahesh0.dev`)**:
  Rather than disabling host verification completely (`allowedHosts: true`), the allowlist uses Vite's leading-dot wildcard syntax (`.modal.host`), which matches any subdomain including `ta-*-3000-*.w.modal.host` and `*-3000.modal.host`. It also includes the Cloudflare Ingress domain (`3000.mahesh0.dev`) to ensure compatibility across both preview networking modes.

- **Dual Placement in Sandbox Runtime**:
  The environment variable `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` is declared in the spawner configuration dictionary (passed directly to container creation) and exported in the container entrypoint script immediately prior to launching the dev server.

- **Universal Dev Preview Scope**:
  The host allowlist configuration is active whenever dev preview mode is enabled, encompassing both Dedicated Preview Sandboxes provisioned from Factory Studio and post-verification dev keep-alive daemons spawned from CLI assembly lines.

- **Remote Template and Repository Synchronization**:
  The canonical TanStack Start template repository and active test repositories within the Test Organization receive direct commits updating their bundler configuration to define the host allowlist explicitly.

- **Non-Blocking Sandbox Termination**:
  Preview termination in the web control plane executes non-blocking asynchronous termination against the container client, avoiding blocking the web framework's asynchronous event loop.

- **ADR Amendment**:
  ADR 0037 is updated to incorporate the host validation findings, trade-offs between wildcard allowlists and permissive bypasses, and the resulting configuration parameters.

## Testing Decisions

- **What makes a good test**:
  Tests should verify external configuration boundaries and observable behaviors (environment variable presence in container specifications, exit codes, API response structures, and non-blocking termination execution) without asserting on private internal loop variables or ephemeral network socket timings.

- **Modules to be tested**:
  - Spawner Engine: Unit and integration tests in the preview test suite verifying that dedicated preview configurations and dev preview sandboxes populate `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS` with the expected wildcard string.
  - UI Server & Preview Registry: API route tests verifying preview launching, status reporting, and non-blocking termination behavior.
  - In-Sandbox Entrypoint Script: Verification that the startup shell script exports the fallback allowlist when the dev keep-alive block is evaluated.

- **Prior art**:
  - `tests/test_preview.py`: Existing Dedicated Preview Sandbox argument inspection and container configuration fixtures.
  - `tests/test_ui.py`: Existing FastAPI preview endpoint integration tests.

## Out of Scope

- Modifying upstream bundler libraries (Vite, esbuild, TanStack Start).
- Disabling DNS rebinding protection globally (`allowedHosts: true`).
- Supporting arbitrary non-preview ingress domains beyond Modal Application Tunnels and the configured Cloudflare Ingress.
- Redesigning Factory Studio UI preview components (viewport toggles, progress steppers, and terminal drawers).

## Further Notes

- Amends ADR 0037 per the architectural decisions settled during the grilling session.
- Adheres strictly to the domain glossary in `CONTEXT.md` (Factory Studio, Dedicated Preview Sandbox, Modal Application Tunnel).
