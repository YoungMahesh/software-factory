# Modal Tunnel Pairing URL and QR Code in T3 Code CLI

**Status**: Accepted (Amends [ADR 0025](0025-t3-code-server-and-agent-control-surface.md), [ADR 0035](0035-multi-account-antigravity-provider-instances-in-t3-code.md), and [ADR 0028](0064-default-antigravity-text-and-source-control-writer-model-in-t3-code.md))

We ensure that running `t3 pair` inside Modal sandboxes provisioned with `--t3` or `--t3code` prints the public Modal HTTPS tunnel URL (e.g. `https://<sandbox-tunnel>.modal.host/pair#token=...`) and encodes the HTTPS URL into the terminal QR code, matching the sandbox launch output and enabling immediate pairing from mobile apps and external browsers.

## Context

When launching Modal sandboxes with `--t3` or `--t3code`, Modal establishes an encrypted application tunnel on port 3775 and prints an instant pairing link and QR code on the host (`t3_pair_url = clean_url + "/pair#token=" + token`).

However, when developers connected into the sandbox via SSH or opened a terminal session and executed `t3 pair`, T3 Code inspected `/root/.t3/userdata/server-runtime.json`. If `devUrl` was missing, T3 Code fell back to inspecting container network interfaces via `NodeOS.networkInterfaces()`, generating a private IP address and unroutable QR code:

```text
Pairing URL: http://172.20.175.235:3775/pair#token=DXTVXNJRCSHY
```

Because `172.20.x.x` is an internal private IP within Modal's virtualization environment, mobile devices scanning the QR code and external browsers could not reach the server. Additionally, executing `t3 pair` from within a repository worktree failed with `NoRunningServerError` unless `--base-dir /root/.t3` was manually specified.

## Considered Options

- **Node SEA Bytecode Patching (`/opt/t3/t3`)**: Modifying the single-executable Node binary's `resolveDirectPairingBaseUrl` function in place via length-preserving string replacements (similar to IPv6 and SSH hostname patches in ADR 0035). Rejected because reading public URLs from environment variables or `/root/.t3/public_url` in JavaScript within exact byte budgets is fragile, prone to SEA offsets corruption, and breaks across T3 Code binary upgrades.
- **Vite Dev Server Flag (`t3 serve --dev-url <url>`)**: Passing the tunnel URL as `--dev-url` at server startup. Rejected because Modal tunnel URLs are only allocated by the host *after* container creation begins, and `--dev-url` instructs T3 Code server to disable its bundled static web client assets in favor of proxying to an external Vite development server.
- **Intelligent CLI Wrapper (`/usr/local/bin/t3`) and Dual-Layer State Synchronization**:
  1. Baking `/usr/local/bin/t3` as a wrapper script in `shared/image.py` (and `shared/t3-wrapper.sh`) delegating to `/opt/t3/t3`.
  2. Resolving the public tunnel URL from `T3_PUBLIC_URL` or `/root/.t3/public_url` and stamping `devUrl` into `/root/.t3/userdata/server-runtime.json`.
  3. Running a 60-second one-shot background watcher in `shared/startup.sh` at container boot to stamp `devUrl` as soon as both `public_url` and `server-runtime.json` appear.
  4. Automatically supplying `--base-dir /root/.t3` when `t3 pair` is called inside subdirectories and worktrees without `--base-dir`.
  Accepted.

## Consequences

- **Image Staging (`shared/image.py` & `shared/t3-wrapper.sh`)**:
  - The wrapper script is pre-installed at `/usr/local/bin/t3` during base image creation and retained in snapshots.
  - Ensures clean delegation to `/opt/t3/t3`.
- **Startup Script (`shared/startup.sh`)**:
  - Launches a bounded one-shot background loop (up to 60s) stamping `devUrl` into `server-runtime.json` once `t3 serve` starts.
  - Leaves no lingering background daemon after initialization finishes.
- **Worktree Usability**:
  - Developers can run `t3 pair` from anywhere in the filesystem (including project root and git worktrees) without manually passing `--base-dir /root/.t3`.
  - User-specified options (such as custom `--base-dir` or `--ttl`) are strictly preserved.
- **Test Integrity**:
  - Corrected heredoc delimiter isolation in `tests/test_sandbox/test_t3_code.py` to prevent unit tests from modifying local host binary paths.
  - Added dedicated unit test suite in `tests/test_sandbox/test_t3_pair.py`.
- **Universal File Line Budget**:
  - All modified files remain strictly compliant with the repository line budget ratchet (ADR 0005 / ADR 0027).
