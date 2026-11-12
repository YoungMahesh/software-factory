# AI Developer Tooling

Modal Sandboxes provides pre-configured integrations for popular AI developer tools and autonomous coding agent harnesses.

## Integrated Tooling Matrix

| Tool | CLI Flag | Port / Ingress | Description |
| :--- | :--- | :--- | :--- |
| **T3 Code** | `--t3` | Port `3775` (Encrypted Tunnel) | Visual coding agent harness with terminal, file editor, and mobile pairing QR. |
| **Antigravity CLI** | `--agy` | Background Daemon | Google Gemini agent CLI and unattended remote control server. |
| **OpenCode Server** | `--opencode` | Port `4096` (HTTPS Tunnel) | Browser-based agent workspace with one-time password auth. |
| **Pi Coding Agent** | `--pi` | System PATH (`pi`) | Lightweight command-line coding assistant. |
| **Herdr Multiplexer**| `--herdr` | `/usr/local/bin/herdr` | Process orchestrator and terminal multiplexer. |
| **Headless Chrome** | `--browser` | Local Headless | Pre-installed Google Chrome for Playwright, Puppeteer, and MCP servers. |

---

## 1. T3 Code Server (`--t3`)

Passing `--t3` provisions the T3 Code server inside the sandbox:
- Starts `t3code` server on internal port `3775`.
- Mounts the persistent Modal volume `t3code-usage-v1` to `/root/.t3/usage` to retain session history across restarts.
- Generates an encrypted pairing URL and prints an ASCII QR code in your terminal on launch.
- Scan the QR code or click the pairing URL to connect your local IDE or browser directly to the sandbox.

```bash
modal-sandbox -r my-repo --t3
```

---

## 2. Google Gemini Antigravity (`--agy`)

Passing `--agy` provisions Google's Antigravity developer agent environment:
- Reads `ANTIGRAVITY_TOKENS` from `.env` and provisions user profiles.
- Configures default writer models (`gemini-2.5-pro` / `gemini-2.5-flash`).
- Starts the Antigravity Remote Control background daemon for unattended agent execution (see [ADR 0002](../adr/0010-antigravity-remote-control-and-unattended-permissions.md)).

```bash
modal-sandbox -r my-repo --agy
```

---

## 3. OpenCode Go Server (`--opencode`)

Passing `--opencode` installs and starts the OpenCode server:
- Listens on port `4096`.
- Connects through an HTTPS tunnel and prints a one-time login password on launch.
- Automatically provisions MCP server credentials via runtime secret injection.

```bash
modal-sandbox -r my-repo --opencode
```

---

## 4. Headless Chrome & Browser MCP (`--browser`)

Passing `--browser` pre-bakes a complete Google Chrome installation and required dependencies into the sandbox image layer (see [ADR 0003](../adr/0009-prebaked-chrome-for-browser-mcp-tooling.md)):
- Compatible with Playwright, Puppeteer, and Chrome DevTools Protocol.
- Enables browser automation tools and MCP servers for visual verification and testing.

```bash
modal-sandbox -r my-repo --browser
```
