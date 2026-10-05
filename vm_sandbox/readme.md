# Modal VM Sandbox with SSH & Web Port Forwarding

Launch a Modal **VM** Sandbox (full Linux kernel, Docker support) with SSH access and a public HTTPS URL for web servers (e.g. Next.js on port 3000). Pass `--opencode` to run an OpenCode server inside the VM sandbox and expose its WebUI over HTTPS, and `--agy` to provision the Antigravity CLI.

For a standard container sandbox without a VM, use [`standard_sandbox/main.py`](../standard_sandbox/main.py) instead.


## Required Modal Secret Variables

The secret collection passed to `--secret-collection` (or `-s`) must define the following environment variables:

| Variable             | Status       | Description                                       | Example            |
| :------------------- | :----------- | :------------------------------------------------ | :----------------- |
| `GH_REPO`            | **Required** | GitHub repository in `owner/repo` format          | `octocat/my-repo`  |
| `GH_TOKEN`           | **Required** | GitHub Personal Access Token for cloning          | `ghp_xxxxxxxxxxxx` |
| `DOTENV_PRIVATE_KEY` | _Optional_   | Key to decrypt `.env.vault` if using dotenv-vault | `dotenv_key_...`   |

> Set these secrets in your Modal dashboard at [modal.com/secrets](https://modal.com/secrets) or via the Modal CLI.

## Quickstart

```bash
# Launch VM sandbox
python main.py --secret-collection <modal-secret-collection-name>

# Launch VM with OpenCode and Antigravity CLI
python main.py --secret-collection <modal-secret-collection-name> --opencode --agy

# Launch VM with Modal Development Tooling (Python 3, venv, Modal SDK, and credentials)
python main.py --secret-collection <modal-secret-collection-name> --modal

# Launch VM with React Native & Android tooling (Metro bundler on port 8081)
python main.py --secret-collection <modal-secret-collection-name> --react-native

# Launch VM with Browser Tooling only (headless Chrome for the browser MCP servers)
python main.py --secret-collection <modal-secret-collection-name> --browser

# Custom web port, OpenCode port, Antigravity CLI, Metro port, and memory allocation
python main.py \
    --secret-collection <modal-secret-collection-name> \
    --opencode \
    --agy \
    --modal \
    --react-native \
    --web-port 3000 \
    --opencode-port 4096 \
    --metro-port 8081 \
    --memory 2
```

`--memory N` allocates `N` GB of RAM to the VM, with a swapfile of `2N` GB (e.g. `--memory 2` -> 2 GB RAM + 4 GB swap). Default: `1`.

SSH access automatically uses `shared/ssh-key.pub` for container authorization and `~/.ssh/modal-sandbox` for client authentication.

Once running, the script prints:

- Standard `modal shell <sandbox-id>` access command
- **Web URL**: Public HTTPS URL forwarding directly to port 3000 inside the sandbox (e.g. `https://<id>-3000.modal.host`)
- **OpenCode Web & Attach Command** (when `--opencode` is passed): Public HTTPS URL and one-time launch password, with attach command:
  ```bash
  OPENCODE_SERVER_PASSWORD=<password> opencode attach <opencode-url>
  ```
- Direct `ssh` command: `ssh -i ~/.ssh/modal-sandbox -o StrictHostKeyChecking=no -p <port> root@<host>`
- VS Code Remote - SSH configuration block

## Agent Tooling & Configuration

- **OpenCode**: Installed via dynamic image layer when `--opencode` is specified. Server runs in background from `/root` on port 4096 (or custom `--opencode-port`). Configured via `shared/opencode.json`.
- **Antigravity CLI**: Installed via dynamic image layer when `--agy` is specified. User configuration and keybindings are mounted from `shared/antigravity-settings.json` and `shared/antigravity-keybindings.json`. Automatically enables SOPS secret decryption inside the sandbox to provision `secrets/antigravity-oauth-token.json` to `~/.gemini/antigravity-cli/antigravity-oauth-token`, launches the background **Antigravity Remote Control** daemon (`https://antigravity.google.com`), configures unattended wildcard permissions in `settings.json`, and aliases `agy` to `--dangerously-skip-permissions` in `~/.bashrc`. Diagnostic checks are available via `check-antigravity`.
- **Browser Tooling**: A headless Google Chrome (`/opt/google/chrome/chrome`) is pre-baked via dynamic image layer when `--browser` is specified, and is implied by `--opencode` and `--agy`. It backs the Playwright and Chrome DevTools MCP servers in `shared/opencode.json`, which run headless with Chrome's sandbox disabled (required under root). The on-demand inspection utility `check-browser` is available at `/usr/local/bin/check-browser`.
- **Code Search**: `ripgrep` is pre-installed in the base Ubuntu VM image for agent text search.

## Running Next.js inside the Sandbox

When you SSH into the sandbox or use `modal shell`, the environment automatically exports:

```bash
HOSTNAME=0.0.0.0
PORT=3000
```

Simply start Next.js: `pnpm run dev`
And open the printed **Web URL** in your browser!

## Running Modal Tooling inside the Sandbox

When started with `--modal`:
- Python 3, `pip`, `venv`, and `python-is-python3` are pre-installed.
- An isolated virtual environment (`.venv`) is provisioned at the repository root and auto-activated across login and interactive shells.
- The `modal` Python client package is pre-installed in `.venv`.
- Project dependencies are installed automatically from `requirements.txt` if present.
- SOPS secret decryption provisions `secrets/modal.toml` into `~/.modal.toml` (mode 0600).
- An on-demand inspection utility `check-modal` (and `check-python`) is available at `/usr/local/bin/check-modal`.

