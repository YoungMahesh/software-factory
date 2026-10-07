# Retire Modal Web Port Tunnel in Favor of Cloudflare Ingress

Previously, the sandbox runner unconditionally configured port 3000 as an encrypted tunnel on Modal (`encrypted_ports = [args.web_port]`), generating an ephemeral public URL (`https://<id>-3000.modal.host`) on every launch alongside the pre-baked Cloudflare Tunnel (`https://3000.mahesh0.dev`). With Cloudflare Tunnel running as the persistent, zero-config default ingress managed by the port watcher daemon, the redundant Modal web tunnel cluttered launch output and confused developers about the canonical access URL. We decided to retire Modal encrypted tunnel creation for port 3000, remove the `--web-port` CLI parameter, standardize local web applications strictly on port 3000 (`PORT=3000`), and rely exclusively on Cloudflare Tunnel for public web ingress across both Standard and VM Sandboxes.

## Considered Options

- **Retain Modal web tunnel as an opt-in CLI flag (`--modal-web-tunnel`)**: Keep the ability to generate ephemeral Modal URLs when explicitly requested. Rejected because the developer preview workflow standardizes on the persistent custom domain `3000.mahesh0.dev`, avoiding fragmented access patterns and maintaining zero-config simplicity.
- **Retain `--web-port` while decoupling it from Modal encrypted ports**: Allow custom container ports (e.g. `--web-port 8000`) for the port watcher and web dev servers while omitting Modal tunnels. Rejected because Cloudflare Tunnel ingress DNS is fixed to `https://3000.mahesh0.dev` and guest web applications standardize on port 3000 via container environment defaults.
- **Retire Modal web tunnel, remove `--web-port`, and enforce port 3000 reservation**: Completely remove port 3000 from Modal `encrypted_ports`, remove `--web-port` from CLI arguments, hardcode `PORT=3000`, validate that other exposed ports (`--opencode-port`, `--metro-port`) do not collide with reserved port 3000, and accept Cloudflare Tunnel connector collisions across concurrent sandboxes. Accepted because it eliminates redundant URLs, streamlines CLI ergonomics, preserves port integrity for the Cloudflare watcher daemon, and establishes a single canonical entrypoint for web applications.

## Consequences

- `sandbox/main.py` removes `--web-port` and no longer requests encrypted tunnels on port 3000 from Modal (`encrypted_ports` only contains opt-in `--opencode-port` and `--metro-port`).
- `PORT` is exported as `"3000"` in the container environment for dev servers and `cloudflared-port-watcher`.
- `--opencode-port` and `--metro-port` reject binding to port 3000 with explicit validation errors.
- `print_access_info` no longer queries or prints `web_url` (`https://<id>-3000.modal.host`), announcing only `• Cloudflare: https://3000.mahesh0.dev (port 3000)` when Cloudflare is active.
- When `--no-cloudflare` is specified, public web ingress is disabled and omitted from launch info.
- Multiple concurrently running sandboxes share the Cloudflare Tunnel connector; developers accept routing collisions if both run dev servers simultaneously on port 3000.
- `sandbox/readme.md` is updated to reflect SSH & Cloudflare Ingress without `--web-port`.
