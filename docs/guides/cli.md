# CLI Reference (`modal-sandbox`)

The `modal-sandbox` CLI is the primary developer interface for provisioning, managing, and snapshotting cloud sandboxes.

## Command Syntax

```bash
modal-sandbox [OPTIONS]
```

---

## Command Options

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-n, --name` | string | `None` | Instance and Modal App name (required for standalone runs). |
| `-r, --repo` | string | `None` | Target GitHub repository (`<owner>/<repo>` or shorthand `<repo>`). |
| `-b, --github-branch` | string | `main` | Git branch to clone and checkout. |
| `--full-clone` | flag | `False` | Perform a full Git clone (default is shallow clone with depth 50). |
| `--vm` | flag | `False` | Provision a Linux VM Sandbox with Docker daemon instead of standard container. |
| `--testing` | flag | `False` | Automatically prepend `test-` prefix to repository name in test organization. |
| `--t3` | flag | `False` | Launch T3 Code server with encrypted pairing URL and ASCII QR code. |
| `--agy` | flag | `False` | Enable Google Gemini Antigravity CLI and Remote Control background daemon. |
| `--opencode` | flag | `False` | Launch OpenCode server on port 4096 with web tunnel. |
| `--pi` | flag | `False` | Install Pi Coding Agent CLI into system PATH. |
| `--herdr` | flag | `False` | Install Herdr agent multiplexer into `/usr/local/bin`. |
| `--browser` | flag | `False` | Pre-bake headless Google Chrome for Playwright and MCP tooling. |
| `--react-native` | flag | `False` | Install Android SDK/NDK, OpenJDK 17, Watchman, and Metro bundler tunnel. |
| `--modal` | flag | `False` | Install Modal SDK and client credentials inside sandbox virtualenv. |
| `--no-cloudflare` | flag | `False` | Disable default Cloudflare Tunnel ingress on port 3000. |
| `--no-ssh-config` | flag | `False` | Do not automatically append SSH connection details to `~/.ssh/config`. |
| `--sops` | flag | `False` | Retain Age private key in `~/.config/sops` for interactive debugging. |
| `--remote` | flag | `False` | Delegate sandbox execution to the hosted Modal control plane function. |
| `--snapshot <id>` | string | `None` | Capture a filesystem snapshot of a running sandbox ID. |
| `--from-snapshot <img-id>` | string | `None` | Launch a fresh sandbox from an existing filesystem snapshot image ID. |
| `--snapshot-ttl <days>` | integer | `30` | Snapshot retention period in days (used with `--snapshot`). |
| `--terminate` | flag | `False` | Terminate the sandbox immediately after taking a snapshot. |

---

## Common Usage Examples

### 1. Launch a Standalone Development Sandbox
```bash
modal-sandbox --name dev-box
```

### 2. Clone a Target Repository with AI Agent Stack
```bash
modal-sandbox -r my-service -b feature-auth --t3 --agy --browser
```

### 3. Launch a Full Linux VM with Docker Daemon
```bash
modal-sandbox --name integration-box --vm
```

### 4. Capture a Snapshot and Terminate
```bash
modal-sandbox --snapshot sb-abcdef123456 --terminate
```

### 5. Resume from Snapshot
```bash
modal-sandbox --from-snapshot im-9876543210 --name resumed-dev
```
