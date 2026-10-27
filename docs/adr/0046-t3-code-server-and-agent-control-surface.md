# T3 Code Server and Agent Control Surface

We added support for T3 Code (`pingdotgg/t3code`) as an opt-in agent control surface running inside Modal sandboxes. Developers can launch sandboxes with `--t3` (or `--t3code`) to run a background headless server (`t3 serve`) bound to default port `3775`, exposed via a dedicated Modal encrypted tunnel, and connected to the target project workspace.

## Considered Options

- **Dynamic install via curl installer script (`curl -fsSL https://t3.codes/install.sh | sh`)**: Rejected in favor of direct pinned GitHub release asset extraction (`t3-0.0.45-linux-x64.tar.gz`) to guarantee deterministic image layering immune to upstream installer script modifications.
- **Global NPM package (`npm install -g t3`)**: Rejected to avoid npm registry download overhead, heavy package dependencies, and ensure the standalone pre-compiled native binary is installed directly into `/opt/t3` and linked at `/usr/local/bin/t3`.
- **Cloudflare Tunnel ingress**: Rejected because Cloudflare Tunnel is reserved for target web application previews on port 3000. T3 Code uses an encrypted Modal application tunnel, matching the pattern of OpenCode Server on port 4096.
- **Mandatory coupling to specific agents**: Rejected because T3 Code acts as an orthogonal control surface that automatically discovers and orchestrates Antigravity (`--agy`) or OpenCode (`--opencode`) when present, while also functioning standalone for worktree inspection and diff reviews.

## Consequences

- `sandbox/main.py` gains `--t3`, `--t3code` (alias), and `--t3-port` (default: 3775).
- Port 3000 is rejected for `--t3-port`, and collisions between `--t3-port`, `--opencode-port`, and `--metro-port` are strictly prevented.
- `shared/image.py` layers the pinned T3 Code distribution into `/opt/t3`, patches the binary to pass `--enforce_kernel_ipv6_support=false` to Antigravity ACP runtime on Linux, and symlinks `/usr/local/bin/t3` when `t3` is requested.
- `shared/startup.sh` launches `t3 serve --host 0.0.0.0 --port "$T3_PORT" --mode web --auto-bootstrap-project-from-cwd "$TARGET_DIR"` in the background, mints a 24-hour client pairing token (`/tmp/t3-pairing.json`), and provisions `/usr/local/bin/check-t3`.
- `print_access_info` outputs the direct 1-click pairing URL (`/pair#token=...`) and renders a terminal unicode ASCII QR code for instant mobile app connection.
