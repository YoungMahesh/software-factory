# Modal Sandbox with SSH & Web Port Forwarding

Launch a Modal sandbox environment with SSH access, a public HTTPS URL for web servers (e.g. Next.js on port 3000), and a default Cloudflare Tunnel (`https://3000.mahesh0.dev`).

The unified runner supports two execution models:
- **Standard Sandbox (Default)**: Lightweight container sandbox on Modal running directly on the container runtime with dynamic burstable memory (128 MiB request up to 16 GiB limit) and fast startup.
- **VM Sandbox (`--vm`)**: Full Linux virtual machine on Modal with custom kernel privileges, Docker daemon support (`ENABLE_DOCKER=1`), and automated swapfile allocation (2× RAM).

---

## Required Modal Secret Variables

### Repository Secret Collection (`--secret-collection` or `-s`)

The repository secret collection passed to `--secret-collection` (or `-s`) must define the following environment variables:

| Variable             | Status       | Description                                       | Example            |
| :------------------- | :----------- | :------------------------------------------------ | :----------------- |
| `GH_REPO`            | **Required** | GitHub repository in `owner/repo` format          | `octocat/my-repo`  |
| `GH_TOKEN`           | **Required** | GitHub Personal Access Token for cloning          | `ghp_xxxxxxxxxxxx` |
| `DOTENV_PRIVATE_KEY` | _Optional_   | Key to decrypt `.env.vault` if using dotenv-vault | `dotenv_key_...`   |

### Shared Workspace Secret (`share0`)

The shared Modal secret named `share0` is automatically mounted by default to decrypt the Cloudflare Tunnel token (`secrets/cloudflare.env`) and whenever credential decryption is requested (`--agy`, `--modal`, or `--opencode`), and must define:

| Variable          | Status                                                                                      | Description                                     | Example               |
| :---------------- | :------------------------------------------------------------------------------------------ | :---------------------------------------------- | :-------------------- |
| `AGE_PRIVATE_KEY` | **Required** (by default for Cloudflare Tunnel, and with `--agy`, `--modal`, `--opencode`) | Master Age private key used for SOPS decryption | `AGE-SECRET-KEY-1...` |

> Set these secrets in your Modal dashboard at [modal.com/secrets](https://modal.com/secrets) or via the Modal CLI. Note: Bare sandboxes without `share0` can be launched by opting out of the Cloudflare Tunnel using `--no-cloudflare`.

---

## Quickstart

```bash
# 1. Launch a Standard Sandbox (default container runtime)
python sandbox/main.py --secret-collection <modal-secret-collection-name>

# 2. Launch a VM Sandbox (full Linux VM with Docker and swap)
python sandbox/main.py --secret-collection <modal-secret-collection-name> --vm

# 3. Launch a VM Sandbox with custom RAM (e.g. 2 GB RAM + 4 GB swap)
python sandbox/main.py --secret-collection <modal-secret-collection-name> --vm --memory 2

# 4. Launch with an OpenCode server (WebUI on port 4096)
python sandbox/main.py --secret-collection <modal-secret-collection-name> --opencode

# 5. Launch with Antigravity CLI and SOPS secrets
python sandbox/main.py --secret-collection <modal-secret-collection-name> --agy

# 6. Launch with Modal Development Tooling (Python 3, venv, Modal SDK, and credentials)
python sandbox/main.py --secret-collection <modal-secret-collection-name> --modal

# 7. Launch with React Native & Android tooling (Metro bundler on port 8081)
python sandbox/main.py --secret-collection <modal-secret-collection-name> --react-native

# 8. Launch with Browser Tooling only (headless Chrome for the browser MCP servers)
python sandbox/main.py --secret-collection <modal-secret-collection-name> --browser

# 9. Full-featured VM launch with custom ports
python sandbox/main.py \
    --secret-collection <modal-secret-collection-name> \
    --vm \
    --memory 2 \
    --opencode \
    --agy \
    --modal \
    --react-native \
    --web-port 3000 \
    --opencode-port 4096 \
    --metro-port 8081
```

SSH access automatically uses `shared/ssh-key.pub` for container authorization and `~/.ssh/modal-sandbox` for client authentication.

Once running, the script prints:
- Standard `modal shell <sandbox-id>` access command
- **Cloudflare Tunnel**: `https://3000.mahesh0.dev` (port 3000, managed via port-watcher daemon)
- **Web URL**: Public HTTPS URL forwarding directly to port 3000 inside the sandbox (e.g. `https://<id>-3000.modal.host`)
- **OpenCode Web & Attach Command** (when `--opencode` is passed): Public HTTPS URL and one-time launch password:
  ```bash
  OPENCODE_SERVER_PASSWORD=<password> opencode --server <opencode-url>
  ```
- **Metro**: Public HTTPS URL forwarding directly to port 8081 when `--react-native` is passed
- **Antigravity Remote Control**: Link to dashboard (`https://antigravity.google.com`) when `--agy` is passed
- Direct `ssh` command: `ssh -i ~/.ssh/modal-sandbox -o StrictHostKeyChecking=no -p <port> root@<host>`
- VS Code Remote - SSH configuration snippet

---

## Agent Tooling & Configuration

- **OpenCode**: Installed via dynamic image layer when `--opencode` is specified. Server runs in background from `/root` on port 4096 (or custom `--opencode-port`). Configured via `shared/opencode.json`.
- **Antigravity CLI**: Installed via dynamic image layer when `--agy` is specified. User configuration and keybindings are mounted from `shared/antigravity-settings.json` and `shared/antigravity-keybindings.json`. Automatically enables SOPS secret decryption inside the sandbox to provision `secrets/antigravity-oauth-token.json` to `~/.gemini/antigravity-cli/antigravity-oauth-token`, launches the background **Antigravity Remote Control** daemon (`https://antigravity.google.com`), configures unattended wildcard permissions in `settings.json`, and aliases `agy` to `--dangerously-skip-permissions` in `~/.bashrc`. Diagnostic checks are available via `check-antigravity`.
- **Browser Tooling**: A headless Google Chrome (`/opt/google/chrome/chrome`) is pre-baked via dynamic image layer when `--browser` is specified, and is implied by `--opencode` and `--agy`. It backs the Playwright and Chrome DevTools MCP servers in `shared/opencode.json`, which run headless with Chrome's sandbox disabled (required under root). The on-demand inspection utility `check-browser` is available at `/usr/local/bin/check-browser`.
- **Code Search**: `ripgrep` is pre-installed in the base Ubuntu image for agent text search.

---

## Running Next.js inside the Sandbox

When you SSH into the sandbox or use `modal shell`, the environment automatically exports:

```bash
HOSTNAME=0.0.0.0
PORT=3000
```

Simply start Next.js: `pnpm run dev`
And open the printed **Web URL** or **Cloudflare Tunnel** in your browser!

---

## Running React Native inside the Sandbox

When started with `--react-native`:
- OpenJDK 17 (`JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`) is pre-installed.
- Android command-line tools, platform-tools, platforms 34 & 35, build-tools 34 & 35, NDK (`26.1.10909125`), and CMake (`3.22.1`) are pre-baked into `/opt/android-sdk`.
- `ANDROID_HOME`, `ANDROID_SDK_ROOT`, `JAVA_HOME`, and `PATH` are pre-configured in both `/etc/environment` and `~/.bashrc`.
- Metro bundler port 8081 (or custom `--metro-port`) is exposed via a secure HTTPS tunnel.
- Diagnostic checks are available via `check-react-native`.

---

## Running Modal Tooling inside the Sandbox

When started with `--modal`:
- Python 3, `pip`, `venv`, and `python-is-python3` are pre-installed.
- An isolated virtual environment (`.venv`) is provisioned at the repository root and auto-activated across login and interactive shells.
- The `modal` Python client package is pre-installed in `.venv`.
- Project dependencies are installed automatically from `requirements.txt` if present.
- SOPS secret decryption provisions `secrets/modal.toml` into `~/.modal.toml` (mode 0600).
- Diagnostic checks are available via `check-modal` (and `check-python`).
