# AI Developer Tooling

Modal Sandboxes provide pre-configured integrations for autonomous coding agent harnesses and browser automation tools, consolidated under **T3 Code** ([ADR 0075](../adr/0075-retire-herdr-pi-opencode-agy-in-favor-of-t3.md)).

## Integrated Tooling Matrix

| Tool | CLI Flag | Port / Ingress | Description |
| :--- | :--- | :--- | :--- |
| **T3 Code** | `--t3` | Port `3775` (Encrypted Tunnel) | Visual coding agent harness with terminal, file editor, worktree orchestration, and mobile pairing QR. Orchestrates Antigravity and OpenCode providers. |
| **Headless Chrome** | `--browser` | Local Headless | Pre-installed Google Chrome for Playwright, Puppeteer, and MCP servers (also implied by `--t3`). |

---

## 1. T3 Code Server (`--t3`)

Passing `--t3` provisions the T3 Code server inside the sandbox:
- Starts `t3code` server on internal port `3775`.
- Mounts persistent Modal volume `t3code-usage-v1` to retain session history, worktrees, and conversation states.
- Generates an encrypted pairing URL and prints an ASCII QR code in your terminal on launch.
- Scan the QR code or click the pairing URL to connect your desktop app, browser, or mobile device directly to the sandbox.

```bash
modal-sandbox -r my-repo --t3
```

### Integrated Providers in T3 Code

When `--t3` is enabled, the sandbox automatically provisions provider backends:
- **Antigravity Provider**: Bundled managed ACP server (`agy_acp_server.par`) provisioned dynamically from `ANTIGRAVITY_TOKENS` via `scripts/setup.sh --t3`.
- **OpenCode Provider**: Pre-baked `/root/.opencode/bin/opencode` binary with configuration and `OPENCODE_GO_API_KEY` injected into `~/.config/opencode/opencode.env`.
- **Developer Command Utilities**: System-wide `agyq` (direct Gemini query CLI) and `agyprofile` (account profile switcher) are available in `/usr/local/bin`.

> [!NOTE]
> Standalone launch flags (`--agy`, `--opencode`, `--pi`, `--herdr`) have been retired in favor of native T3 Code orchestration (see [ADR 0075](../adr/0075-retire-herdr-pi-opencode-agy-in-favor-of-t3.md)).

---

## 2. Headless Chrome & Browser MCP (`--browser`)

Passing `--browser` pre-bakes a complete Google Chrome installation and required dependencies into the sandbox image layer (see [ADR 0009](../adr/0009-prebaked-chrome-for-browser-mcp-tooling.md)):
- Automatically enabled when `--t3` is passed.
- Compatible with Playwright, Puppeteer, and Chrome DevTools Protocol.
- Enables browser automation tools and MCP servers for visual verification and testing.

```bash
modal-sandbox -r my-repo --browser
```
