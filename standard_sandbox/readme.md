# Modal Sandbox with SSH & Web Port Forwarding

Launch a Modal sandbox container with SSH access and a public HTTPS URL for web servers (e.g. Next.js on port 3000). Pass `--opencode` to additionally run an OpenCode server inside the sandbox and expose its WebUI over HTTPS, or `--react-native` to enable the Android development toolchain and Metro bundler tunnel.

For a full Linux VM Sandbox with Docker support, use [`vm_sandbox/main.py`](../vm_sandbox/main.py) instead.


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
# Launch standard sandbox (default)
python main.py --secret-collection <modal-secret-collection-name>

# Launch with an OpenCode server (WebUI on port 4096)
python main.py --secret-collection <modal-secret-collection-name> --opencode

# Launch with React Native & Android tooling (Metro bundler on port 8081)
python main.py --secret-collection <modal-secret-collection-name> --react-native

# Launch with Antigravity CLI and SOPS secrets
python main.py --secret-collection <modal-secret-collection-name> --agy

# Custom web port, Metro port, and OpenCode port
python main.py \
    --secret-collection <modal-secret-collection-name> \
    --react-native \
    --opencode \
    --web-port 3000 \
    --metro-port 8081 \
    --opencode-port 4096
```

SSH access automatically uses `shared/ssh-key.pub` for container authorization and `~/.ssh/modal-sandbox` for client authentication.

Once running, the script prints:

- Standard `modal shell <sandbox-id>` access command
- **Web URL**: Public HTTPS URL forwarding directly to port 3000 inside the sandbox (e.g. `https://<id>-3000.modal.host`)
- **Metro**: Public HTTPS URL forwarding directly to port 8081 inside the sandbox when `--react-native` is passed (e.g. `https://<id>-8081.modal.host`)
- Direct `ssh` command: `ssh -i ~/.ssh/modal-sandbox -o StrictHostKeyChecking=no -p <port> root@<host>`
- VS Code Remote - SSH configuration block

## Agent Tooling & Configuration

- **OpenCode**: Installed via dynamic image layer when `--opencode` is specified. Server runs in background from `/root` on port 4096 (or custom `--opencode-port`). Configured via `shared/opencode.json`.
- **Antigravity CLI**: Installed via dynamic image layer when `--agy` is specified. User configuration and keybindings are mounted from `shared/antigravity-settings.json` and `shared/antigravity-keybindings.json`. Automatically enables SOPS secret decryption inside the sandbox to provision `secrets/antigravity-oauth-token.json` to `~/.gemini/antigravity-cli/antigravity-oauth-token`.
- **Code Search**: `ripgrep` is pre-installed in the base image for agent text search.

## Running Next.js inside the Sandbox

When you SSH into the sandbox or use `modal shell`, the environment automatically exports:

```bash
HOSTNAME=0.0.0.0
PORT=3000
```

Simply start Next.js: `pnpm run dev`
And open the printed **Web URL** in your browser!

## Running React Native inside the Sandbox

When started with `--react-native`:
- OpenJDK 17 (`JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`) is pre-installed.
- Android command-line tools, platform-tools, platforms 34 & 35, build-tools 34 & 35, NDK (`26.1.10909125`), and CMake (`3.22.1`) are pre-baked into `/opt/android-sdk`.
- `ANDROID_HOME`, `ANDROID_SDK_ROOT`, `JAVA_HOME`, and `PATH` are pre-configured in both `/etc/environment` and `~/.bashrc`.
- Metro bundler port 8081 (or custom `--metro-port`) is exposed via a secure HTTPS tunnel.
