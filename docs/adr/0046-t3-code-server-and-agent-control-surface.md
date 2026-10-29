# T3 Code Server and Agent Control Surface

We added support for T3 Code (`pingdotgg/t3code`) as an opt-in agent control surface running inside Modal sandboxes. Developers can launch sandboxes with `--t3` (or `--t3code`) to run a background headless server (`t3 serve`) bound to default port `3775`, exposed via a dedicated Modal encrypted tunnel, and connected to the target project workspace.

## Considered Options

- **Dynamic install via curl installer script (`curl -fsSL https://t3.codes/install.sh | sh`)**: Rejected in favor of direct pinned GitHub release asset extraction (`t3-0.0.45-linux-x64.tar.gz`) to guarantee deterministic image layering immune to upstream installer script modifications.
- **Global NPM package (`npm install -g t3`)**: Rejected to avoid npm registry download overhead, heavy package dependencies, and ensure the standalone pre-compiled native binary is installed directly into `/opt/t3` and linked at `/usr/local/bin/t3`.\n- **Cloudflare Tunnel ingress**: Rejected because Cloudflare Tunnel is reserved for target web application previews on port 3000. T3 Code uses an encrypted Modal application tunnel, matching the pattern of OpenCode Server on port 4096.
- **Mandatory coupling to specific agents**: Rejected because T3 Code acts as an orthogonal control surface that automatically discovers and orchestrates Antigravity (`--agy`) or OpenCode (`--opencode`) when present, while also functioning standalone for worktree inspection and diff reviews.

## Consequences

- `sandbox/main.py` gains `--t3`, `--t3code` (alias), and `--t3-port` (default: 3775).
- Port 3000 is rejected for `--t3-port`, and collisions between `--t3-port`, `--opencode-port`, and `--metro-port` are strictly prevented.
- `shared/image.py` layers the pinned T3 Code distribution into `/opt/t3` and symlinks `/usr/local/bin/t3` when `t3` is requested.
- `shared/startup.sh` launches `t3 serve --host 0.0.0.0 --port "$T3_PORT" --mode web --auto-bootstrap-project-from-cwd "$TARGET_DIR"` in the background, mints a 24-hour client pairing token (`/tmp/t3-pairing.json`), and provisions `/usr/local/bin/check-t3`.
- `print_access_info` outputs the direct 1-click pairing URL (`/pair#token=...`) and renders a terminal unicode ASCII QR code for instant mobile app connection.

## Amendments

- **2026-10-27**: Upgraded pinned release from `0.0.45` to `0.1.3` (`t3-0.1.3-linux-x64.tar.gz`).
- **2026-10-27**: Pre-downloaded and staged Google's Antigravity ACP runtime `1.3.0` (`9fb60956af0a9d76220a4db91ca9ac88e2a2372ad68f985ab5fceace6b825b96`) into `/root/.t3/tools/antigravity-acp/linux-x64/` with `.install-complete.json` and `active.json` at image build time to eliminate on-demand web UI downloads. Restored the `--enforce_kernel_ipv6_support=false` launch argument patch via an exact length-preserving in-place patch (183 to 183 bytes) to satisfy gVisor networking without corrupting or truncating the Node SEA bundle.
- **2026-10-27**: Added automatic pre-authentication for Antigravity in T3 Code when decrypted OAuth credentials (`antigravity-oauth-token`) are present. Reuses the shared Google Cloud OAuth client credentials to synthesize `/root/.t3/userdata/providers/antigravity/<sha256>/antigravity-acp/acp_token.json` and `settings.json`, enabling seamless sign-in without manual browser interaction.
- **2026-10-27**: Added automatic pre-seeding of provider status cache (`/root/.t3/caches/antigravity.json`) on container boot when decrypted Antigravity credentials are present. This allows T3 Code's `hydrateCachedProvider` and `carrySavedAntigravityAccount` to initialize Antigravity directly in the "ready" and "authenticated" state, eliminating the initial manual "Sign in" click in the web UI.
- **2026-10-27**: Added automatic pre-configuration for OpenCode Go subscription in T3 Code when `--t3` is used and encrypted credentials (`secrets/opencode.env`) are present. OpenCode CLI (`/root/.opencode/bin/opencode`) and configuration files (`shared/opencode.json`) are bundled into the image. During bootstrap, `secrets/opencode.env` is decrypted via SOPS, `OPENCODE_GO_API_KEY` is exported, and `/root/.t3/userdata/settings.json` is configured with `providerInstances.opencode` in managed mode (`binaryPath: "/root/.opencode/bin/opencode"`), enabling OpenCode Go models dynamically alongside Antigravity while gracefully degrading if keys are absent.
- **2026-10-29**: Fixed SSH remote open target resolution in T3 Code for Modal sandboxes. Upstream T3 Code defaults to mDNS (`${shortHostname}.local`), producing broken links like `vscode-remote://ssh-remote+root@modal.local/...` because Modal container hostnames default to `modal`. Implemented an exact length-preserving in-place patch (248 to 248 bytes) in `/opt/t3/t3` to check `process.env.T3_SSH_HOST` or `process.env.SANDBOX_NAME` for the SSH host alias, matching the SSH configuration snippet printed at launch (`Host {instance_name}`). Pre-configured `/etc/machine-info` with `PRETTY_HOSTNAME` so T3 Code displays the sandbox name instead of `modal` in the project environment dropdown. Added optional `--t3-ssh-host` flag to `sandbox/main.py` and `sandbox/cli.py` to allow custom SSH host alias overrides.
