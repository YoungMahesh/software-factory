# Modal Sandbox with SSH & Web Port Forwarding

Launch a Modal sandbox container with SSH access and a public HTTPS URL for web servers (e.g. Next.js on port 3000). Pass `--opencode` to additionally run an OpenCode server inside the sandbox and expose its WebUI over HTTPS.

For a full Linux VM Sandbox with Docker support, use [`vm_sandbox/launch_vm-ssh.py`](../vm_sandbox/launch_vm-ssh.py) instead.


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
python launch-with-ssh.py --secret-collection <modal-secret-collection-name>

# Launch with an OpenCode server (WebUI on port 4096)
python launch-with-ssh.py --secret-collection <modal-secret-collection-name> --opencode

# Custom SSH key, web port and OpenCode port
python launch-with-ssh.py \
    --secret-collection <modal-secret-collection-name> \
    --opencode \
    --ssh-key ~/.ssh/id_ed25519 \
    --web-port 3000 \
    --opencode-port 4096
```

Once running, the script prints:

- Standard `modal shell <sandbox-id>` access command
- **Web URL**: Public HTTPS URL forwarding directly to port 3000 inside the sandbox (e.g. `https://<id>-3000.modal.host`)
- Direct `ssh` command: `ssh -i <key> -o StrictHostKeyChecking=no -p <port> root@<host>`
- VS Code Remote - SSH configuration block

## Running Next.js inside the Sandbox

When you SSH into the sandbox or use `modal shell`, the environment automatically exports:

```bash
HOSTNAME=0.0.0.0
PORT=3000
```

Simply start Next.js: `pnpm run dev`
And open the printed **Web URL** in your browser!
