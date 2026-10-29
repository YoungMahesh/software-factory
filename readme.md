# Modal Sandboxes

Toolkit for provisioning, managing, and snapshotting isolated cloud execution environments on Modal with SSH, Cloudflare Tunnel ingress, and integrated AI developer tooling.

---

## 1. Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
bash scripts/setup.sh --modal --agy --opencode
```

Decrypts versioned credentials via local SOPS into standard user paths (`~/.modal.toml`, `~/.gemini/antigravity-cli/`, `~/.config/opencode/`).

---

## 2. Launching Sandboxes

The **Unified Sandbox Runner** ([`sandbox/main.py`](sandbox/main.py)) is the canonical entry point:

```bash
# Repository Sandbox (clones repo from encrypted fetch credentials)
python sandbox/main.py -s <secret-name> [flags]

# Standalone Sandbox (boots clean environment without repo clone)
python sandbox/main.py --name <app-name> [flags]

# Linux VM Sandbox with Docker and swapfile allocation
python sandbox/main.py -s <secret-name> --vm --memory 2

# Sandbox with Agent & Tooling Environments
python sandbox/main.py -s <secret-name> --opencode --t3 --agy
```

### Core CLI Flags

| Flag | Description | Default |
| :--- | :--- | :--- |
| `-s, --secret` | Repository secret name under `secrets/<secret-name>/fetch.env` | None |
| `--name` | Modal App name (required for standalone and snapshot resumes) | None |
| `-b, --github-branch` | Git branch to checkout | `main` |
| `--full-clone` | Fetch complete commit history (default is shallow depth 50) | `False` |
| `--vm` | Provision a Linux VM Sandbox with Docker daemon instead of container | `False` |
| `--memory <GB>` | RAM allocation in GB (for VM sandboxes; allocates 2× swap) | `1` |
| `--testing` | Target repositories under test organization `software-factory-09-test` | `False` |
| `--opencode` | Launch OpenCode server on port 4096 with web tunnel | `False` |
| `--t3` | Launch T3 Code server with pairing token and web tunnel | `False` |
| `--agy` | Enable Antigravity CLI and Antigravity Remote Control daemon | `False` |
| `--pi` | Install Pi Coding Agent CLI | `False` |
| `--herdr` | Install Herdr terminal multiplexer | `False` |
| `--modal` | Provision Modal Development Tooling (`modal` SDK & credentials) | `False` |
| `--react-native` | Android toolchain (SDK/NDK/Java 17) and Metro tunnel (port 8081) | `False` |
| `--browser` | Headless Google Chrome for browser MCP tooling | `False` |
| `--sops` | Retain Age private key in `~/.config/sops` for interactive debugging | `False` |
| `--no-cloudflare` | Disable default Cloudflare Tunnel ingress on port 3000 | `False` |

---

## 3. Filesystem Snapshots

Capture copy-on-write root filesystem images of running sandboxes for near-instant cold starts:

```bash
# Capture snapshot from an active sandbox
python sandbox/main.py --snapshot <sandbox-id> [--snapshot-ttl 30] [--terminate]

# Resume/launch directly from a snapshot image
python sandbox/main.py --from-snapshot <image-id> --name resumed-app [--vm]
```

---

## 4. Access & Ingress

- **SSH**: Uses tracked public key [`shared/ssh-key.pub`](shared/ssh-key.pub) and private key `~/.ssh/modal-sandbox`:
  ```bash
  ssh -i ~/.ssh/modal-sandbox -p <port> root@<host>
  # Or via Modal CLI:
  modal shell <sandbox-id>
  ```
- **Web Ingress (Port 3000)**: Pre-configured Cloudflare Tunnel routes `https://3000.mahesh0.dev` to container `localhost:3000`.
- **OpenCode (Port 4096)**: HTTPS tunnel URL and one-time password printed on launch when `--opencode` is passed.
- **T3 Code Server**: Pairing URL and QR code printed on launch when `--t3` is passed.

---

## 5. Sandbox Lifecycle Management

```bash
# List active running sandboxes
python scripts/list-sandboxes.py

# Interactive management & termination CLI
python scripts/manage_sandboxes.py
```

---

## 6. Verification & Automated Tests

```bash
pytest tests/test_sandbox tests/test_manage_sandboxes.py
```
