# AI Developer Tooling

Modal Sandboxes provide pre-configured integrations for autonomous coding agent harnesses and browser automation tools, consolidated under **T3 Code** ([ADR 0075](../adr/0075-retire-herdr-pi-opencode-agy-in-favor-of-t3.md)).

## Integrated Tooling Matrix

| Tool | CLI Flag | Port / Ingress | Description |
| :--- | :--- | :--- | :--- |
| **T3 Code** | `--t3` | Port `3775` (Encrypted Tunnel) | Visual coding agent harness with terminal, file editor, worktree orchestration, and mobile pairing QR. Orchestrates Antigravity (`gemini-4-hydrogen` default builder model), OpenCode, and Codex providers. |
| **Headless Chromium** | `--browser` | Local Headless | Pre-baked Playwright Chromium for headless browser automation and MCP tooling (also implied by `--t3`, which adds `/opt/t3/t3 browser setup`). Full Google Chrome is installed separately by `--xfce`. |

---

## 1. T3 Code Server (`--t3`)

Passing `--t3` provisions the T3 Code server inside the sandbox:
- Starts the T3 Code server (`t3 serve`) on internal port `3775`.
- Mounts `t3code-usage-v1` at `/root/.t3-storage` and synchronizes supported conversation state, provider transcripts, and usage caches. Arbitrary repository files and worktrees require Git or filesystem snapshots.
- Generates an encrypted pairing URL and prints an ASCII QR code in your terminal on launch.
- Scan the QR code or click the pairing URL to connect your desktop app, browser, or mobile device directly to the sandbox.

```bash
modal-sandbox -r my-repo --t3
```

### Integrated Providers in T3 Code

When `--t3` is enabled, the sandbox automatically provisions provider backends:
- **Antigravity Provider**: Official Antigravity CLI runtime staged under `/root/.t3/tools/antigravity-acp/linux-x64`; startup configures accounts from `ANTIGRAVITY_TOKENS`. The older PAR runtime is historical (see [ADR 0076](../adr/0076-t3-code-v0-1-11-and-official-antigravity-cli-runtime.md)).
- **OpenCode Provider**: Pre-baked `/root/.opencode/bin/opencode` binary with configuration and `OPENCODE_GO_API_KEY` injected into `~/.config/opencode/opencode.env`.
- **Codex Provider**: Pre-installed Codex CLI on newly built T3 images. Use `codexprofile login` to sign in through ChatGPT.
- **Developer Command Utilities**: System-wide `agyq` (direct Gemini query CLI) and `agyprofile` (account profile switcher) are available in `/usr/local/bin`.

> [!NOTE]
> Standalone launch flags (`--agy`, `--opencode`, `--pi`, `--herdr`) have been retired in favor of native T3 Code orchestration (see [ADR 0075](../adr/0075-retire-herdr-pi-opencode-agy-in-favor-of-t3.md)).

---

### Persistence and connection options

Use `--t3-port` to change the server port and `--t3-ssh-host` to select the SSH alias used in editor links. `--t3-usage-volume <name>` selects the history volume; `--no-t3-persist` disables history synchronization. These require `--t3`, and the last two options are mutually exclusive. Codex credential profiles are configured independently of T3 history persistence.

### Codex login profiles

Set `CODEX_PROFILE_VOLUME_PREFIX` in the factory environment to enable three saved login profiles in the selected Modal workspace and environment. The launcher creates volumes with suffixes `-a`, `-b`, and `-c`, using a separate prefix for `--testing`. Start launches one at a time. A running sandbox keeps its profile until Modal reports that it has exited.

- `codexprofile current` prints the profile attached to this sandbox.
- `codexprofile login` starts device sign-in for this sandbox and saves the session on its assigned volume. With no attached profile, the login is local to the sandbox.
- `codexprofile status` shows the local login and which sandbox owns each profile if pool-wide status is configured. A saved login indicates a credential file is present. If the session stops working, sign in again from the sandbox holding that profile. An unknown owner keeps the profile unavailable until the launcher can verify its last sandbox.

For pool-wide status, set the HTTPS `MODAL_SANDBOX_ENDPOINT_URL` and a random `CODEX_STATUS_SECRET` on both the launch host and the hosted control plane. Configure both for the same Modal workspace and environment. The launch host gives the sandbox a credential that only grants access to the profile status endpoint.

## 2. Headless Chromium & Browser Tooling (`--browser`)

Passing `--browser` pre-bakes Playwright Chromium (`uvx playwright install --with-deps chromium`) and system browser libraries into the sandbox image layer:
- Automatically enabled when `--t3` is passed (which also runs `/opt/t3/t3 browser setup`).
- Compatible with Playwright and headless browser automation tools inside containers without a display server.
- Separate from `--xfce`, which installs full Google Chrome (`google-chrome-stable`) on desktop VMs (see [ADR 0070](../adr/0070-xfce-desktop-and-chrome-in-vm-sandboxes.md) and [runtimes](../architecture/runtimes.md)).

```bash
modal-sandbox -r my-repo --browser
```
