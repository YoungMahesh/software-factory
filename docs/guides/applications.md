# Application Creation and Deployment

`create-app` materializes the canonical `app-template/` blueprint into an independent application repository. It supports a Next.js 16 web app, optional Expo mobile client, Drizzle database setup, Better Auth, shared theme/types packages, and allowlisted agent skills.

## Local scaffolding

Install the factory CLI, Git, Node.js, and pnpm. The generated package manifest declares Node.js 20+ and pnpm 10.31.0; ensure your Node version also meets the generated Next.js package's requirements. Sandbox base images include Node.js 24 and pnpm.

```bash
# A web demo without database or authentication setup.
create-app my-demo --no-db --no-auth -y
cd my-demo
pnpm dev
```

For a full-stack application, `create-app my-app` prompts on an interactive terminal when no option flags are supplied. Defaults enable the database, authentication, skills, installation, and Git; mobile is opt-in. `-y` selects defaults without prompts. Git commit creation requires configured authorship.

```bash
create-app my-app --mobile-app -y
# Inside an empty standalone sandbox workspace:
create-app . -y
```

Configure `DATABASE_URL` before using database-backed features. The generated app loads app-local and repository-root `.env` values. `--no-install` skips dependency installation. `--force` permits an existing nonempty destination; inspect that directory before using it. See the [CLI option reference](cli.md#application-scaffolding-create-app).

The template directory is a blueprint excluded from the factory pnpm workspace. Build and run the generated application in its destination, rather than running pnpm against `app-template/` itself. Sandboxes receive a copy of the blueprint at `/opt/app-template`.

## Optional cloud wiring

| Action | Prerequisites |
| :--- | :--- |
| Create/push GitHub repository | `GH_TOKEN` with repository creation/push access, `GH_ORG_NAME` or explicit owner in `--repo-name`, and Git authorship |
| Provision PostgreSQL or S3 | Deployed Resource Plane, `RESOURCE_PLANE_DOMAIN`, `RESOURCE_PLANE_ADMIN_TOKEN` |
| Push secrets to Central Config Store (`config/env/`) | GitHub write access to the private `config` repository and SOPS available; launch host needs an Age key to decrypt the vault later |
| Launch development sandbox | Authenticated Modal client using the selected Modal Profile, launch-host SSH public-key file, and GitHub access to the pushed repository |
| Deploy a Hosted App | Deployment host SSH key, VPS Docker, Caddy wildcard ingress, and the configuration described below |

```bash
create-app my-app --cloud -y
create-app my-mobile-app --cloud --mobile-app --provision-s3 -y
```

`--cloud` enables GitHub repository creation, database provisioning when the database overlay is enabled, pushing `.env` to the vault, and launching a T3 sandbox. S3 and production deployment remain opt-in. Each operation can also be selected independently with `--github`, `--provision-db`, `--provision-s3`, `--push-vault`, `--launch`, or `--deploy`.

Cloud operations execute in sequence and are not one transaction. If a later step fails, inspect resources already created before retrying. `--launch` can target an existing repository with `--repo-name owner/name`; push the scaffolded files there before relying on that repository as the launch source.

The launched sandbox and any Hosted App have separate lifetimes. CLI scaffolding and cloud wiring do not create a Builder Workspace record; that identity belongs to the dashboard Builder workflow.

## Prepare VPS deployment

Run `deploy-app` from the deployment host with the explicit VPS SSH key. A developer working in a sandbox can push code and vault updates, then deploy that repository from the host. The factory checkout's `.env` supplies deployment settings:

```env
RESOURCE_PLANE_SSH_HOST=203.0.113.10
RESOURCE_PLANE_SSH_USER=root
RESOURCE_PLANE_SSH_KEY=.secrets/resource_plane_ssh
APPS_BASE_DOMAIN=apps.example.com
CLOUDFLARE_DNS_API_TOKEN=your-dns-token
```

Use a VPS user with access to `/root/<repo-name>`, Docker, and `/opt/caddy`. Configure the apex and wildcard DNS records for the base domain to point at the VPS, and allow Caddy's public HTTPS ingress. Bootstrap infrastructure and wildcard ingress using the [Resource Plane deployment guide](resource-plane-deployment.md):

```bash
modal-sandbox infra deploy
modal-sandbox infra caddy --bootstrap --wildcard --domain resources.example.com
```

The token must permit DNS changes for the relevant Cloudflare zone. Caddy stores it at `/opt/caddy/.env`, excluded from Central Config Store (`config/caddy/`) backups. The wildcard certificate covers the configured base domain and its immediate subdomains: `modal-sandbox infra dashboard` serves the production Next.js Sandbox Web Dashboard from `https://<APPS_BASE_DOMAIN>` while routing `/launch`, `/snapshot`, `/health`, and `/api/codex/profiles` to Modal, `modal-sandbox infra deployer` serves the standalone Dashboard Deployer on `https://deploy.<APPS_BASE_DOMAIN>`, and `<repo-name>.<APPS_BASE_DOMAIN>` routes Hosted Apps reusing that certificate (`deploy` and `docs` are reserved subdomains under `APPS_BASE_DOMAIN`, with `docs.<APPS_BASE_DOMAIN>` served by Cloudflare Pages).

## Deploy or redeploy

```bash
# Transfer a local generated app.
deploy-app ./my-app

# Pull committed source and vault configuration from GitHub on the deployment host.
deploy-app --repo my-org/my-app --branch main

# Choose another hostname and back up the resulting proxy configuration.
deploy-app ./my-app --subdomain preview --sync
```

Both modes deploy to `/root/<repo-name>` by default, build the app's `docker-compose.yml`, and run `<app-slug>-web` on `dbhost-network`. The command stages the Resource Plane CA when available, rewrites container CA paths, sets the public web/mobile URLs, runs the template's Drizzle migration when present, starts the container, checks readiness, and activates a Caddy snippet at `/opt/caddy/conf/apps/<app-slug>.caddy`.

Local mode starts with the remote `.env` and overlays the local `.env`; a local `.env.example` is only a fallback when no other environment is available. GitHub mode overlays resolved vault values onto the existing remote environment. Review credentials before deployment: example placeholders are not production configuration. `--skip-migrate` skips the migration step; it does not make source or database changes reversible.

Use the same command to redeploy. To roll source back, check out the desired source locally and redeploy that directory, or point GitHub mode at a branch containing the desired version. Database schema/data rollback must be handled separately.

## Ownership and recovery

Hosted App ownership is tracked independently of Builder Workspace records and sandbox lifetime. Deploy and teardown serialize mutations with a VPS deployment lock and ownership records under `/opt/caddy/.factory-apps/`. The command checks repository identity, existing container labels, and route ownership before mutation. It refuses conflicting ownership, unverifiable legacy directories, and hostnames already assigned to another app. `--subdomain` can resolve a hostname conflict, but cannot bypass an app-name ownership conflict; use a distinct repository name when separate apps would produce the same slug.

Caddy changes use validation, a lock, and a recovery journal at `/opt/caddy/.factory-ingress-pending`. A failed activation attempts to restore the previous configuration. After an interrupted update, the next mutating ingress operation retries recovery before applying changes. Preserve pending files if recovery reports a failure. A successful route rollback does not roll back source transfers, builds, or database migrations from earlier deployment steps.

For troubleshooting, inspect the app stack and proxy on the VPS:

```bash
cd /root/my-app
docker compose -p my-app ps
docker compose -p my-app logs --tail=100
cd /opt/caddy
docker compose logs --tail=100
```

## Stop or remove an app

```bash
# Stop containers and remove the public Caddy route; retain source and .env.
deploy-app down my-app

# Also remove the remote app directory and release its ownership record.
deploy-app down my-app --purge
```

These commands do not delete Resource Plane databases, S3 buckets, GitHub repositories, or vault files. Caddy Store backups preserve ingress declarations rather than app source or database contents. See the [CLI reference](cli.md#deploying-hosted-apps-deploy-app) for connection overrides and flags.
