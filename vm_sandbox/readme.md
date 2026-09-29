# Modal VM Sandbox with SSH & Web Port Forwarding

Launch a Modal **VM** Sandbox (full Linux kernel, Docker support) with SSH access and a public HTTPS URL for web servers (e.g. Next.js on port 3000). Pass `--opencode` to run an OpenCode server inside the VM sandbox and expose its WebUI over HTTPS, and `--agy` to provision the Antigravity CLI.

For a standard container sandbox without a VM, use [`standard_sandbox/launch-with-ssh.py`](../standard_sandbox/launch-with-ssh.py) instead.


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
python launch_vm-ssh.py --secret-collection <modal-secret-collection-name>

# Launch VM with OpenCode and Antigravity CLI
python launch_vm-ssh.py --secret-collection <modal-secret-collection-name> --opencode --agy

# Custom SSH key, web port, OpenCode port, and memory allocation
python launch_vm-ssh.py \
    --secret-collection <modal-secret-collection-name> \
    --opencode \
    --agy \
    --ssh-key ~/.ssh/id_ed25519 \
    --web-port 3000 \
    --opencode-port 4096 \
    --memory 2
```

`--memory N` allocates `N` GB of RAM to the VM, with a swapfile of `2N` GB (e.g. `--memory 2` -> 2 GB RAM + 4 GB swap). Default: `1`.

Once running, the script prints:

- Standard `modal shell <sandbox-id>` access command
- **Web URL**: Public HTTPS URL forwarding directly to port 3000 inside the sandbox (e.g. `https://<id>-3000.modal.host`)
- **OpenCode Web & Attach Command** (when `--opencode` is passed): Public HTTPS URL and one-time launch password, with attach command:
  ```bash
  OPENCODE_SERVER_PASSWORD=<password> opencode attach <opencode-url>
  ```
- Direct `ssh` command: `ssh -i <key> -o StrictHostKeyChecking=no -p <port> root@<host>`
- VS Code Remote - SSH configuration block

## Agent Tooling & Configuration

- **OpenCode**: Installed via dynamic image layer when `--opencode` is specified. Server runs in background from `/root` on port 4096 (or custom `--opencode-port`). Configured via `vm_sandbox/opencode.json`.
- **Antigravity CLI**: Installed via dynamic image layer when `--agy` is specified. User configuration and keybindings are mounted from `vm_sandbox/settings.json` and `vm_sandbox/keybindings.json`. Pre-authenticates if `vm_sandbox/antigravity-oauth-token` is present.
- **Code Search**: `ripgrep` is pre-installed in the base Ubuntu VM image for agent text search.

## Running Next.js inside the Sandbox

When you SSH into the sandbox or use `modal shell`, the environment automatically exports:

```bash
HOSTNAME=0.0.0.0
PORT=3000
```

Simply start Next.js: `pnpm run dev`
And open the printed **Web URL** in your browser!
