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
| **Repository Fetch Secret** | `secrets/<secret-name>/fetch.env` | `GH_REPO`, `GH_TOKEN` (opt: `DOTENV_PRIVATE_KEY`) | Git clone credentials. |
| **Repository Environment Secrets** | `secrets/<secret-name>/env.map` | `<encrypted_file>=<repo_relative_dest>` | Multi-application `.env` file provisioning. |

---

## 2. Launching Sandboxes

```bash
python sandbox/main.py -s <secret-name> [flags]
```

| Flag | Description | Default |
| :--- | :--- | :--- |
| `-s, --secret` | Repository secret name under `secrets/<secret-name>/fetch.env` | *Required* |
| `--testing` | Use credentials from Test Organization (`software-factory-09-test`) | `False` |
| `--vm` | Provision a VM Sandbox with Docker daemon instead of a Standard Sandbox | `False` |
| `--memory <GB>` | RAM allocation in GB (VM sandboxes only; 2× swap) | `1` |
| `--opencode` | OpenCode server on port 4096 with WebUI tunnel | `False` |
| `--agy` | Antigravity CLI and Antigravity Remote Control daemon (`antigravity.google.com`) | `False` |
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
- **Metro Bundler (Port 8081)**: HTTPS tunnel URL printed on launch when `--react-native` is passed.
