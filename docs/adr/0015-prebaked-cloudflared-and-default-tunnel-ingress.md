# Pre-baked Cloudflared and Default Tunnel Ingress

Previously, sandboxes relied solely on ephemeral Modal tunnels (`sandbox.tunnels()[web_port].url`) or direct SSH connections to access web applications running inside the container. We decided to pre-bake the standalone `cloudflared` binary into the Shared Base Image and start Cloudflare Tunnel as a background service by default during sandbox bootstrap. The service automatically routes external HTTPS traffic from the persistent custom domain `https://3000.mahesh0.dev` directly to local port 3000 across all Standard and VM Sandboxes without requiring open inbound firewall ports.

## Considered Options

- **Runtime installation in `startup.sh` on every launch**: Download and install `cloudflared` dynamically during sandbox boot. Rejected because downloading binaries at startup introduces latency and external network failure modes to every sandbox boot.
- **Opt-in CLI flag `--cloudflare`**: Require an explicit `--cloudflare` flag to install or run the tunnel. Rejected because developer preview workflow requires the persistent custom domain `3000.mahesh0.dev` out of the box by default for zero-config iteration.
- **Pre-baked binary with port-aware watcher daemon and `--no-cloudflare` escape hatch**: Pre-bake `/usr/local/bin/cloudflared` into the Shared Base Image in `shared/image.py`. In `shared/startup.sh`, configure the service and supervise it via a background port watcher daemon (`cloudflared-port-watcher`). The watcher monitors `/dev/tcp/127.0.0.1/$PORT`, starting `cloudflared` only when an application binds to the port and stopping it immediately when the port closes. Add a `--no-cloudflare` opt-out flag to `standard_sandbox/main.py` and `vm_sandbox/main.py` to prevent connector registration entirely when desired. Accepted because it delivers instant boot times, 100% Modal layer cache reuse, zero-config default availability, and completely eliminates 502/connection-refused collisions from idle sandboxes.

## Consequences

- `shared/image.py` pre-bakes `/usr/local/bin/cloudflared` in `base_image`, shared by both Standard and VM Sandboxes.
- `shared/startup.sh` configures Cloudflare Tunnel early during Step 0 via `cloudflared service install`, guarded by `ENABLE_CLOUDFLARE != 0` and protected with idempotency checks against duplicate service creation.
- A background daemon `cloudflared-port-watcher` continuously polls the local port (default: 3000): starting `cloudflared` dynamically when the local dev server starts and stopping it when the dev server stops, ensuring idle sandboxes do not hijack traffic.
- A fallback tunnel token is configured in `shared/startup.sh`, while allowing overrides via the `CLOUDFLARE_TUNNEL_TOKEN` environment variable.
- An inspection utility `check-cloudflare` (aliased to `check-cf`) is created in `/usr/local/bin/` inside the sandbox to inspect version, service status, running processes, port watcher status, and token configuration.
- `standard_sandbox/main.py` and `vm_sandbox/main.py` provide `--no-cloudflare` to disable tunnel startup and connector registration.
- `print_access_info` announces `• Cloudflare: https://3000.mahesh0.dev (port 3000)` upon sandbox readiness.

## Amendments

- **Non-Intrusive Socket Monitoring**: The port watcher daemon in `shared/startup.sh` was amended from raw TCP socket writing (`echo > /dev/tcp/127.0.0.1/$PORT`) to inspecting `/proc/net/tcp` for listening sockets (`0A`). This eliminates spurious `Invalid HTTP request received` warnings in HTTP servers like Uvicorn caused by raw newline probes while preserving dynamic tunnel startup and shutdown.
- **Zombie Process Rejection in Init Script**: In container environments where PID 1 does not reap re-parented child processes, terminated cloudflared daemons linger as defunct zombies. Because `ps <pid>` succeeds on zombie processes in `/proc`, `/etc/init.d/cloudflared` falsely treated dead processes as active, failing to delete `/var/run/cloudflared.pid` and preventing `cloudflared-port-watcher` from starting the daemon when target ports activate. `shared/startup.sh` was amended to patch `/etc/init.d/cloudflared` to verify that the PID is alive and not in a zombie state (`State: Z` in `/proc/$PID/status`), and to cleanly unlink stale PID files.

