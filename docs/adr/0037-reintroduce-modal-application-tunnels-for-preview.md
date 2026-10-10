# Reintroduce Modal Application Tunnels for Concurrent Application Previews

**Status**: Accepted (Amends ADR 0021 and ADR 0034)

To support instant, concurrent web application previews in Factory Studio without routing collisions on the singleton Cloudflare Ingress (`https://3000.mahesh0.dev`), we decided to re-introduce Modal encrypted tunnels for container port 3000 (`encrypted_ports=[3000]`), generating an ephemeral, isolated HTTPS URL (`https://<sandbox-id>-3000.modal.host`) per preview sandbox.

Modern frontend build tools and development servers (specifically Vite versions 5.4.12+ and 6/7/8) enforce strict HTTP Host header validation to guard against DNS rebinding attacks. Because Modal Application Tunnels generate dynamic, unique subdomains under `.modal.host` that are not pre-configured in project repositories, development servers reject incoming preview traffic with host block errors unless explicitly permitted. To resolve this without compromising DNS rebinding protection, we adopt a defense-in-depth scoped wildcard allowlist architecture across the software factory preview infrastructure.

## Considered Options

- **Retaining Exclusive Cloudflare Tunnel Ingress (`https://3000.mahesh0.dev`)**: Relying only on Cloudflare Ingress per ADR 0021. Rejected because Cloudflare Ingress is bound to a single tunnel token and domain, causing severe connector collisions and disconnect flapping when developers preview multiple projects or inspect an application while an assembly line run is active.
- **Dynamic Multi-Domain Cloudflare Tunnel Allocation**: Programmatically minting subdomains or tunnel credentials per sandbox. Rejected because it requires external Cloudflare API management and introduces cloud credential proliferation into ephemeral sandboxes.
- **Modal Encrypted Tunnels for Port 3000 (`encrypted_ports=[3000]`)**: Accepted because Modal natively generates a secure, unique HTTPS tunnel URL per container upon creation (`sandbox.tunnels()[3000].url`). It introduces zero third-party latency, does not enforce restrictive framing headers, isolates concurrent project previews, and allows Factory Studio to host multiple running applications simultaneously.
- **Permissive Host Validation Bypass (`allowedHosts: true`)**: Disabling dev server host validation entirely. Rejected because disabling host checks globally weakens DNS rebinding attack protections on development containers.
- **Scoped Wildcard Allowlist (`.modal.host,3000.mahesh0.dev`)**: Accepted because Vite's leading-dot wildcard syntax (`.modal.host`) strictly matches all Modal Application Tunnel subdomains (including `ta-*-3000-*.w.modal.host` and `*-3000.modal.host`) while explicitly permitting Cloudflare Ingress (`3000.mahesh0.dev`), preserving DNS rebinding security.

## Consequences

- ADR 0021 is amended: Modal encrypted tunnels for port 3000 are re-introduced specifically for Dedicated Preview Sandboxes and Factory Studio live previews.
- Dedicated Preview Sandboxes run with `ENABLE_CLOUDFLARE=0`, eliminating cloudflared handshake overhead and preventing collision with any background jobs using `https://3000.mahesh0.dev`.
- Factory Studio embeds the unique Modal Application Tunnel URL (`https://<sandbox-id>-3000.modal.host`) inside the `LivePreview` iframe.
- A defense-in-depth host authorization strategy is enforced:
  - **Runtime Injection**: Container spawner configurations inject `__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS=".modal.host,3000.mahesh0.dev"` into preview environments (both Dedicated Preview Sandboxes and CLI assembly lines running with `--dev`). The container entrypoint script (`factory_entrypoint.sh`) exports this variable with identical defaults before launching the dev server.
  - **Repository Configuration**: Canonical templates (`tanstack-start-template`) and active test repositories (`calculator-app`) explicitly declare `server: { allowedHosts: ['.modal.host', '3000.mahesh0.dev'] }` in `vite.config.ts`.
- Dedicated Preview Sandbox termination in the server registry uses non-blocking asynchronous calls (`await sandbox.terminate.aio()`), preventing synchronous event-loop blocking warnings in web server logs.
- The in-memory registry manages a per-repository preview state, allowing developers to switch between repositories in Factory Studio and immediately interact with active previews.
- Dedicated Preview Sandboxes default to a 30-minute idle timeout on Modal, alongside an explicit termination control in the preview toolbar.
