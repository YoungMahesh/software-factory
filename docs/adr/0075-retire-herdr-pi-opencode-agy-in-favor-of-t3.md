# Retire Standalone Herdr, Pi, OpenCode Server, and Antigravity CLI in Favor of T3 Code Integration

**Status**: Accepted (Amends [ADR 0002](0002-shared-agent-configs-and-sops-antigravity-token.md), [ADR 0005](0005-decouple-setup-flags-and-retire-sops-flag.md), [ADR 0009](0009-prebaked-chrome-for-browser-mcp-tooling.md), [ADR 0025](0025-t3-code-server-and-agent-control-surface.md), and [ADR 0034](0034-pi-coding-agent-cli-integration.md))

We retire the standalone sandbox launch flags and daemon configurations `--herdr`, `--pi`, `--opencode`, `--opencode-port`, and `--agy`, consolidating on **T3 Code** (`--t3`) as the unified developer control surface and agent orchestration platform. We preserve the internal OpenCode CLI binary installation and Antigravity ACP managed bundle strictly inside `--t3` containers, while completely removing legacy standalone daemons, web ports, and unused agent CLIs.

## Context

Over time, multiple disparate AI coding assistants and multiplexer tools were added to Modal Sandboxes:
1. **Herdr Multiplexer (`--herdr`)**: A terminal multiplexer and agent coordinator installed via install script into `/usr/local/bin`.
2. **Pi Coding Agent (`--pi`)**: An interactive terminal-native agent CLI (`pi.dev`) installed via npm and configured with OpenCode Go.
3. **OpenCode Server (`--opencode`, `--opencode-port`)**: A standalone web daemon listening on port 4096 exposed via Modal HTTPS tunnel with dynamic password generation.
4. **Antigravity CLI (`--agy`)**: The Google Gemini Antigravity CLI installed via `antigravity.google/cli/install.sh`, running an unattended background daemon (`agy remote-control start`).

With the introduction and stabilization of **T3 Code** ([ADR 0025](0025-t3-code-server-and-agent-control-surface.md)), developers interact with sandboxes through T3 Code's unified desktop and mobile interface:
- T3 Code directly manages agent providers. For Antigravity, T3 Code spawns a bundled, managed ACP server (`agy_acp_server.par`) rather than invoking the `antigravity-cli` binary.
- For OpenCode, T3 Code spawns the local binary `/root/.opencode/bin/opencode` as its provider backend, but does not use the standalone `opencode serve` web server or port 4096 tunnel.
- Developer command-line utilities (`agyq` and `agyprofile`) operate directly against Gemini APIs and profile configurations independently of the Antigravity CLI binary.
- Herdr and Pi are redundant given T3 Code's integrated multi-agent orchestration, thread management, and terminal worktrees.

Maintaining separate `--herdr`, `--pi`, `--opencode`, and `--agy` launch flags created unnecessary CLI clutter, bloated container images, introduced port collision risks, and maintained deprecated background daemons and config files.

## Decisions

1. **Remove Standalone CLI Flags & Models**:
   - Remove `--herdr`, `--pi`, `--opencode`, `--opencode-port`, and `--agy` from `sandbox/cli.py`, `sandbox/core.py`, `sandbox/launcher.py`, `sandbox/main.py`, and `sandbox/web.py`.
   - Remove these flags and their default form states from the Web UI (`sandbox/static/index.html`).
   - Remove `DEFAULT_OPENCODE_PORT` (4096) and port collision logic related to OpenCode.

2. **Streamline `scripts/setup.sh`**:
   - `scripts/setup.sh` now accepts only `--modal` and `--t3`.
   - When `--t3` is passed, `setup.sh` ephemerally decrypts `secrets/opencode.env` (if present) to populate `OPENCODE_GO_API_KEY` at `~/.config/opencode/opencode.env` and configures T3 Code provider settings for Antigravity and OpenCode.
   - Remove `--agy`, `--pi`, and all references to `SETUP_PI` from `setup.sh`.

3. **Preserve Internal T3 Dependencies in Container Image**:
   - In `shared/image.py`, when `t3=True`:
     - Install the OpenCode binary (`curl -fsSL https://opencode.ai/v2/install | bash`) so T3 Code can spawn `/root/.opencode/bin/opencode`.
     - Stage `shared/opencode.json` to `/root/.config/opencode/opencode.json`.
     - Stage the managed Antigravity ACP bundle (`T3_ANTIGRAVITY_URL`) to `/root/.t3/tools/antigravity-acp/...`.
     - Export `/root/.opencode/bin` on PATH.
   - Omit the standalone `antigravity-cli` binary installation, Herdr install script, and Pi npm package.
   - Delete obsolete asset and config files: `shared/antigravity-settings.json`, `shared/antigravity-keybindings.json`, `shared/antigravity-onboarding.json`, `shared/pi-settings.json`, and `shared/pi-models.json`.

4. **Retain Developer Productivity Scripts**:
   - Retain `scripts/agyq` (Gemini API querying) and `scripts/agyprofile` (profile switcher) as system-wide commands in `/usr/local/bin` across all sandboxes.

5. **Clean Container Boot Sequence (`shared/startup.sh`)**:
   - Remove background service loops and startup daemons for `ENABLE_ANTIGRAVITY` (`agy remote-control start`), `ENABLE_OPENCODE` (`opencode serve`), and `ENABLE_PI`.
   - Only launch T3 Code server and XFCE desktop (when enabled).

6. **Browser Tooling Precedence**:
   - Simplify `browser_enabled(*, browser: bool = False, t3: bool = False) -> bool`. Chrome browser tooling is provisioned when `--browser` is passed explicitly or when `--t3` is enabled.

## Consequences

- **Simplified Launch Interface**: Launch arguments are streamlined to core sandbox features (`--t3`, `--browser`, `--react-native`, `--modal`, `--xfce`, `--sops`, `--vm`).
- **Faster Image Builds & Smaller Size**: Image build steps no longer download or compile Herdr, Pi, or `antigravity-cli`.
- **Zero Port Collisions on 4096**: Port 4096 is completely freed and eliminates port conflict checks.
- **Unified Agent Surface**: All agent interaction is channeled through T3 Code's cohesive native experience.
- **Strict Universal Line Budget**: All modified files remain $\le 500$ physical lines.
