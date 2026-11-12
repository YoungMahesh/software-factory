# T3 Code Pairing Tunnel Wrapper and Unit Test Isolation Boundary

**Status**: Accepted (Amends [ADR 0042](0042-modal-tunnel-pairing-url-in-t3-code-cli.md) and [ADR 0055](0055-packaging-dx-and-open-source-governance.md))

We establish strict test isolation for container startup tests to prevent host binary pollution, ensure `/usr/local/bin/t3` cleanly delegates with `unset GH_REPO` and Modal HTTPS tunnel URL injection, and extend post-boot pairing synchronization timeouts.

## Context

In ADR 0042, we established an intelligent CLI wrapper at `/usr/local/bin/t3` (backed by `shared/t3-wrapper.sh`) to inject `devUrl` into `/root/.t3/userdata/server-runtime.json` and auto-supply `--base-dir /root/.t3` when `t3 pair` is executed from project subdirectories and git worktrees. This guarantees that `t3 pair` emits the public Modal HTTPS tunnel URL (e.g. `https://<sandbox-tunnel>.modal.host/pair#token=...`) and terminal QR code.

However, when developers ran `t3 pair` inside active Modal sandboxes, the CLI occasionally regressed to printing internal private IP addresses:

```text
Pairing URL: http://172.20.3.77:3775/pair#token=ULWQAEEVBQ59
```

Root-cause diagnosis identified three interconnected faults:

1. **Test Environment Leakage and Host Binary Overwrites**: Several unit test suites (`tests/test_sandbox/test_snapshots.py`, `tests/test_sandbox/test_cli_args.py`, and `tests/test_sandbox/test_tooling_precedence.py`) simulated container startup by running `startup.sh` with `sed 's|/root|{fake_root}|g'`. Because the tests ran inside an active Modal sandbox where `ENABLE_T3=1` was exported in the process environment, and `/usr/local/bin` was not redirected to a test-isolated directory, `startup.sh`'s inline heredoc wrote directly to the host container's `/usr/local/bin/t3`. The wrapper's file paths were populated with `{fake_root}` pointing to a temporary directory (`.../antigravity-tmp/.../tmpXXXXXX`) that was destroyed when the test finished. Once deleted, `/usr/local/bin/t3` could not locate `/root/.t3/public_url` or `server-runtime.json`, failing silently and falling back to Node's internal network interfaces (`172.20.x.x`).
2. **Wrapper Inconsistency (`unset GH_REPO`)**: The inline heredoc in `shared/startup.sh` included `unset GH_REPO` so T3 Code resolves repositories dynamically from git remotes rather than the launch-time repository name, but `shared/t3-wrapper.sh` lacked this statement.
3. **Host-to-Container Pairing Timing Race**: In `sandbox/t3.py`, `setup_t3()` attempted to poll `/tmp/t3-pairing.json` for only 3 seconds (6 iterations × 0.5s). On fresh sandbox launches where dependency installation (`git clone`, `sops`, `pnpm install`, `requirements.txt`) required 20–40 seconds before `t3 serve` started, host setup timed out prematurely.

## Decisions

1. **Strict Test Environment Isolation Boundary**:
   - Every unit test executing `startup.sh` in a subprocess must explicitly neutralize service daemons (`ENABLE_T3="0"`, `ENABLE_ANTIGRAVITY="0"`, `ENABLE_OPENCODE="0"`, `ENABLE_MODAL="0"`, `ENABLE_SOPS="0"`, `ENABLE_PI="0"`, `ENABLE_REACT_NATIVE="0"`, `ENABLE_HERDR="0"`).
   - In addition to replacing `/root` with `{fake_root}`, all test startup scripts must redirect `/usr/local/bin` to an isolated `{fake_bin}` directory (`-e 's|/usr/local/bin|{fake_bin}|g'`).
   - Added a regression test in `tests/test_sandbox/test_t3_pair.py` asserting that running startup simulations leaves `/usr/local/bin/t3` unmodified.

2. **Canonical T3 Wrapper Parity**:
   - Updated `shared/t3-wrapper.sh` to include `unset GH_REPO`, ensuring parity with `shared/startup.sh`.
   - The wrapper checks `T3_PUBLIC_URL` or `/root/.t3/public_url`, stamps `devUrl` into `server-runtime.json`, and automatically injects `--base-dir /root/.t3` when called within repository worktrees.

3. **Extended Pairing Credential Polling**:
   - In `sandbox/t3.py`, increased `/tmp/t3-pairing.json` retry polling from 3 seconds to 25 seconds (25 iterations × 1.0s), accommodating container boot and package installation latency.

## Consequences

- Executing `t3 pair` anywhere in the container (root or worktrees) reliably displays the Modal tunnel pairing URL and QR code.
- Running the unit test suite inside a development sandbox never pollutes or mutates host binaries in `/usr/local/bin`.
- All modified files remain strictly compliant with the universal <= 500 line budget ratchet (ADR 0005 / ADR 0027 / AGENTS.md).
