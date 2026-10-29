# Modal Sandboxes

Ephemeral cloud execution environments on Modal with SSH access and default Cloudflare Tunnel ingress (`https://3000.mahesh0.dev` → port 3000).

- **Standard Sandbox (Default)**: Container runtime with dynamic burstable memory (up to 16 GiB).
- **VM Sandbox (`--vm`)**: Linux virtual machine with Docker daemon (`ENABLE_DOCKER=1`), Docker Compose v2, and swapfile allocation (2× RAM).

---

## 1. Secrets Configuration

Decrypted ephemerally inside the sandbox during boot and scrubbed before shell handoff:

| Secret | Source | Required Keys | Purpose |
| :--- | :--- | :--- | :--- |
| **Shared Workspace Secret** | Modal secret `share0` | `AGE_PRIVATE_KEY` | Master Age key used to decrypt versioned secrets. |
| **Organization Credentials** | `secrets/github-orgs.env` | `<ORG>_GH_TOKEN` (e.g. `SFACTORY0_GH_TOKEN`) | GitHub repository authentication and cloning. |
| **In-Repo Secret Manifest** | `.secrets/env.map` (in repo) | `<encrypted_file>=<repo_relative_dest>` | Multi-application `.env` file provisioning. |

---

## 2. Launching Sandboxes

```bash
python sandbox/main.py -r <repo-name> [flags]
```

| Flag | Description | Default |
| :--- | :--- | :--- |
| `-r, --repo` | Target GitHub repository name (e.g. `sFactory0/<repo>` or `<repo>`) | None |
| `--name` | Modal App name (mandatory for standalone launches without `-r/--repo`) | None |
| `-b, --github-branch` | Git branch to checkout (only branches supported; tags and commits rejected) | `main` |
| `--full-clone` | Fetch complete commit history (default is shallow depth 50) | `False` |
| `--testing` | Target repository under canonical organization `sFactory0` using `test-` prefix | `False` |
| `--vm` | Provision a VM Sandbox with Docker daemon instead of a Standard Sandbox | `False` |
| `--memory <GB>` | RAM allocation in GB (VM sandboxes only; 2× swap) | `1` |
| `--opencode` | OpenCode server on port 4096 with WebUI tunnel | `False` |
| `--t3` | T3 Code server with pairing token and WebUI tunnel | `False` |
| `--agy` | Antigravity CLI and Antigravity Remote Control daemon (`antigravity.google.com`) | `False` |
| `--pi` | Install Pi coding agent CLI | `False` |
| `--herdr` | Install Herdr agent multiplexer | `False` |
| `--modal` | Modal Development Tooling (Python 3, venv, Modal SDK, client credentials) | `False` |
| `--react-native` | Android toolchain (SDK/NDK/Java 17) and Metro bundler tunnel on port 8081 | `False` |
| `--browser` | Headless Google Chrome for browser MCP tooling (implied by `--opencode`/`--agy`) | `False` |
| `--sops` | Retain Age private key in `~/.config/sops` for interactive debugging | `False` |
| `--no-cloudflare` | Disable default Cloudflare Tunnel ingress | `False` |

---

## 3. Access & Ingress

- **SSH**: Uses tracked public key `shared/ssh-key.pub` and client private key `~/.ssh/modal-sandbox`:
  ```bash
  ssh -i ~/.ssh/modal-sandbox -p <port> root@<host>
  # Or via Modal CLI:
  modal shell <sandbox-id>
  ```
- **Web Ingress (Port 3000)**: Pre-configured Cloudflare Tunnel routes `https://3000.mahesh0.dev` to `localhost:3000`.
- **OpenCode (Port 4096)**: HTTPS tunnel URL and one-time password printed on launch when `--opencode` is passed.
- **T3 Code (Port 3775)**: HTTPS pairing URL and ASCII QR code printed on launch when `--t3` is passed.
- **Metro Bundler (Port 8081)**: HTTPS tunnel URL printed on launch when `--react-native` is passed.

---

## 4. Live Testing Verification

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
