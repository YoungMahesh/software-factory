# Modal Sandbox with SSH & Cloudflare Ingress

Launch a Modal sandbox environment with SSH access and a default Cloudflare Tunnel (`https://3000.mahesh0.dev`) routing to local port 3000.

The unified runner supports two execution models:
- **Standard Sandbox (Default)**: Lightweight container sandbox on Modal running directly on the container runtime with dynamic burstable memory (128 MiB request up to 16 GiB limit) and fast startup.
- **VM Sandbox (`--vm`)**: Full Linux virtual machine on Modal with custom kernel privileges, Docker daemon support (`ENABLE_DOCKER=1`), and automated swapfile allocation (2× RAM).

---

## Required Secret Configuration

### Repository Fetch Secret (`--secret` or `-s`)

The repository fetch secret is stored as a SOPS-encrypted file at `secrets/<secret-name>/fetch.env`. It is baked into the container image at `/root/secrets/fetch.env` and decrypted in memory during sandbox boot using `AGE_PRIVATE_KEY` before being scrubbed from disk.

The encrypted `fetch.env` must define the following environment variables:

| Variable             | Status       | Description                                       | Example            |
| :------------------- | :----------- | :------------------------------------------------ | :----------------- |
| `GH_REPO`            | **Required** | GitHub repository in `owner/repo` format          | `octocat/my-repo`  |
| `GH_TOKEN`           | **Required** | GitHub Personal Access Token for cloning          | `ghp_xxxxxxxxxxxx` |
| `DOTENV_PRIVATE_KEY` | _Optional_   | Key to decrypt `.env.vault` if using dotenv-vault | `dotenv_key_...`   |

### Repository Environment Secrets (`env.map`)

For repositories that require `.env` files (e.g. monorepos with multiple applications), co-locate SOPS-encrypted `.env` files under `secrets/<secret-name>/` and map them to their relative file paths inside the repository via `secrets/<secret-name>/env.map`:

```ini
# secrets/<secret-name>/env.map
# <source_encrypted_file>=<repo_relative_destination_path>
web.env=apps/web/.env
mobile.env=apps/mobile/.env
```

During startup, `startup.sh` parses `env.map`, creates any necessary parent directories, decrypts each file using `AGE_PRIVATE_KEY`, sets `chmod 600`, and purges all staging files from `/root/secrets/repo/` before interactive handoff.

### Shared Workspace Secret (`share0`)

The shared Modal secret named `share0` is mounted unconditionally across all sandboxes to decrypt the Repository Fetch Secret (`secrets/<secret-name>/fetch.env`), the Cloudflare Tunnel token (`secrets/cloudflare.env`), and opt-in credentials (`--agy`, `--modal`, or `--opencode`), and must define:

| Variable          | Status       | Description                                     | Example               |
| :---------------- | :----------- | :---------------------------------------------- | :-------------------- |
| `AGE_PRIVATE_KEY` | **Required** | Master Age private key used for SOPS decryption | `AGE-SECRET-KEY-1...` |

> Set `share0` in your Modal dashboard at [modal.com/secrets](https://modal.com/secrets) or via the Modal CLI.

---

## Quickstart

```bash
# 1. Launch a Standard Sandbox (default container runtime)
python sandbox/main.py --secret <secret-name>

# 2. Launch a VM Sandbox (full Linux VM with Docker and swap)
python sandbox/main.py --secret <secret-name> --vm

# 3. Launch a VM Sandbox with custom RAM (e.g. 2 GB RAM + 4 GB swap)
python sandbox/main.py --secret <secret-name> --vm --memory 2

# 4. Launch with an OpenCode server (WebUI on port 4096)
python sandbox/main.py --secret <secret-name> --opencode

# 5. Launch with Antigravity CLI and SOPS secrets
python sandbox/main.py --secret <secret-name> --agy

# 6. Launch with Modal Development Tooling (Python 3, venv, Modal SDK, and credentials)
python sandbox/main.py --secret <secret-name> --modal

# 7. Launch with React Native & Android tooling (Metro bundler on port 8081)
python sandbox/main.py --secret <secret-name> --react-native

# 8. Launch with Browser Tooling only (headless Chrome for the browser MCP servers)
python sandbox/main.py --secret <secret-name> --browser

# 9. Full-featured VM launch with custom ports
python sandbox/main.py \
    --secret <secret-name> \
    --vm \
    --memory 2 \
    --opencode \
    --agy \
    --modal \
    --react-native \
    --opencode-port 4096 \
    --metro-port 8081
```

SSH access automatically uses `shared/ssh-key.pub` for container authorization and `~/.ssh/modal-sandbox` for client authentication.

Once running, the script prints:
- Standard `modal shell <sandbox-id>` access command
- **Cloudflare Tunnel**: `https://3000.mahesh0.dev` (port 3000, managed via port-watcher daemon)
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
And open the **Cloudflare Tunnel** (`https://3000.mahesh0.dev`) in your browser!

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
