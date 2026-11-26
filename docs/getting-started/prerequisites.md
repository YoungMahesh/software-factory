# Prerequisites and Setup

## Install the factory CLI

Use Linux, macOS, or WSL2 with Python 3.11+, Git, and an OpenSSH client. The sandbox base image uses Ubuntu 24.04 with Python 3.12.

```bash
git clone https://github.com/sFactory0/software-factory.git
cd software-factory
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
modal setup
modal-sandbox --help
```

`requirements.txt` installs the package with both `dev` and `docs` extras. A minimal runtime installation is `python -m pip install -e .`; test and documentation dependencies are optional for that installation.

`modal setup` authenticates the launch host. A basic standalone launch does not require `.env` or `MODAL_TOKENS`. The `--modal` option separately enables Modal tooling inside the sandbox and requires valid `MODAL_TOKENS`.

## Prepare SSH access

The launcher authorizes the public key read from `sandboxes/shared/ssh-key.pub`. You need its matching private key at `~/.ssh/modal-sandbox`, with permissions `0600`. The repository does not contain that private key.

If you do not have the matching key, create a dedicated pair and replace the launch host's public-key file before launching:

```bash
# Use an unused filename; ssh-keygen prompts before overwriting an existing key.
ssh-keygen -t ed25519 -f ~/.ssh/modal-sandbox
cp ~/.ssh/modal-sandbox.pub sandboxes/shared/ssh-key.pub
chmod 600 ~/.ssh/modal-sandbox
```

For hosted launches, the operator must redeploy the control plane with the selected public-key file. Startup generates SSH **server host keys**, not the client key pair. An authenticated Modal client can also connect with `modal shell <sandbox-id>`.

## Configure optional integrations

```bash
cp .env.example .env
```

| Workflow | Configuration |
| :--- | :--- |
| Clone a repository | `GH_TOKEN`; `GH_ORG_NAME` for shorthand names |
| Cloudflare application ingress | `CLOUDFLARE_TUNNEL_TOKEN` and an existing tunnel route to port 3000; optional display hostname `MODAL_SANDBOX_TUNNEL_DOMAIN` |
| Hosted sandbox control plane | `WEB_UI_USERNAME` and `WEB_UI_PASSWORD`, both required |
| Modal tooling inside a sandbox | `MODAL_TOKENS` and the `--modal` option |
| Application secrets from Central Config Store (`config/env/`) | GitHub vault access and an Age decryption key on the launch host |
| Database and S3 provisioning | `RESOURCE_PLANE_DOMAIN` and `RESOURCE_PLANE_ADMIN_TOKEN` |
| VPS deployment | `RESOURCE_PLANE_SSH_HOST` and explicit `RESOURCE_PLANE_SSH_KEY` |

Without a Cloudflare token, sandbox startup skips that tunnel. Use `--no-cloudflare` when you only need SSH or the separate T3 Code HTTPS endpoint.

See [environment variables](../reference/environment.md) and [secrets](../architecture/secrets.md) for scope and precedence. Node.js and pnpm are needed for [application scaffolding](../guides/applications.md) and [Resource Plane local development](../guides/resource-plane-deployment.md#local-development).
