# Modal Sandboxes

Toolkit for provisioning, managing, and snapshotting isolated cloud execution environments on Modal with SSH, Cloudflare Tunnel ingress, and integrated AI developer tooling.

---

## 1. Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
bash scripts/setup.sh --modal --agy --opencode
```

Decrypts versioned credentials via local SOPS into standard user paths (`~/.modal.toml`, `~/.gemini/antigravity-cli/`, `~/.config/opencode/`).

---

## 2. Launching Sandboxes

The **Unified Sandbox Runner** ([`sandbox/main.py`](sandbox/main.py)) is the canonical entry point:

```bash
# Repository Sandbox (clones repo from encrypted fetch credentials)
python sandbox/main.py -r <repo-name> [flags]

# Standalone Sandbox (boots clean environment without repo clone)
python sandbox/main.py --name <app-name> [flags]

# Linux VM Sandbox with Docker and swapfile allocation
python sandbox/main.py -r <repo-name> --vm --memory 2

# Sandbox with Agent & Tooling Environments
python sandbox/main.py -r <repo-name> --opencode --t3 --agy
```

### Core CLI Flags

| Flag | Description | Default |
| :--- | :--- | :--- |
| `-r, --repo` | Target GitHub repository name (e.g. `sFactory0/<repo>` or `<repo>`) | None |
| `--name` | Modal App name (required for standalone and snapshot resumes) | None |
| `-b, --github-branch` | Git branch to checkout | `main` |
| `--full-clone` | Fetch complete commit history (default is shallow depth 50) | `False` |
| `--vm` | Provision a Linux VM Sandbox with Docker daemon instead of container | `False` |
| `--memory <GB>` | RAM allocation in GB (for VM sandboxes; allocates 2× swap) | `1` |
| `--testing` | Target repository under canonical organization `sFactory0` using `test-` prefix | `False` |
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
| `--no-ssh-config` | Do not automatically append SSH connection details to `~/.ssh/config` | `False` |

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

- **SSH**: Uses tracked public key [`shared/ssh-key.pub`](shared/ssh-key.pub) and private key `~/.ssh/modal-sandbox`. On launch, connection details are automatically appended to `~/.ssh/config` (skip with `--no-ssh-config`):
  ```bash
  ssh <instance_name>
  # Or with explicit port/key:
  ssh -i ~/.ssh/modal-sandbox -p <port> root@<host>
  # Or via Modal CLI:
  modal shell <sandbox-id>
  ```
- **Web Ingress (Port 3000)**: Pre-configured Cloudflare Tunnel routes `https://3000.mahesh0.dev` to container `localhost:3000`.
- **OpenCode (Port 4096)**: HTTPS tunnel URL and one-time password printed on launch when `--opencode` is passed.
- **T3 Code Server**: Pairing URL and QR code printed on launch when `--t3` is passed.

---

## 5. Sandbox Lifecycle & Control Plane

### CLI Management

```bash
# List active running sandboxes
python scripts/list-sandboxes.py

# Interactive management & termination CLI
python scripts/manage_sandboxes.py
```

### Hosted Control Plane & Web Dashboard

The Web Dashboard and management API run in the cloud via Modal:

```bash
# Deploy control plane to Modal Cloud (requires WEB_UI_USERNAME and WEB_UI_PASSWORD)
modal deploy sandbox/function.py

# Interactive development serve mode
modal serve sandbox/function.py
```

- **Web Dashboard**: Access `GET /` with HTTP Basic Authentication (`WEB_UI_USERNAME` / `WEB_UI_PASSWORD`).
- **Headless API**: Access `POST /launch` and `POST /snapshot` with Bearer token authentication (`MODAL_SANDBOX_AUTH_TOKEN`).

---

## 6. Verification & Automated Tests

### Automated Unit & Subsystem Tests

```bash
pytest tests/test_sandbox tests/test_manage_sandboxes.py
```

### Sandbox Live Verification

When verifying changes to `sandbox/main.py` against live Modal cloud infrastructure, all runs adhere to the **Sandbox Live Verification** standard:

- **Target Repository**: Strictly uses the **Test Repository Baseline** (`sFactory0/test-live-test1`) via Organization credentials (`secrets/github-orgs.env`).
- **Automated Verification**:
  ```bash
  python scripts/test_live_sandbox.py
  ```
  Launches an ephemeral sandbox with a short timeout (300s), verifies token decryption and git checkout (`/root/test-live-test1`), asserts environment invariants, and guarantees immediate teardown in `finally:`.
- **Manual Ad-hoc Verification**:
  ```bash
  # Launch test sandbox
  python sandbox/main.py -r test1 --testing

  # Verify git clone inside sandbox
  modal sandbox exec <sandbox-id> test -d /root/test-test1

  # Immediately terminate to prevent lingering compute charges
  modal sandbox terminate <sandbox-id>
  ```
