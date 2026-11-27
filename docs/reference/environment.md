# Environment Variables Reference

Factory configuration starts with the repository root `.env`; copy the tracked [`.env.example`](https://github.com/YoungMahesh/software-factory/blob/main/.env.example) when configuring integrations. Resource Plane server credentials belong to its own runtime environment, described below.

## Factory and sandbox variables

| Variable | Purpose and default |
| :--- | :--- |
| `WEB_UI_USERNAME`, `WEB_UI_PASSWORD` | Both required for hosted sandbox dashboard and API Basic authentication; no implicit username default |
| `MODAL_TOKENS` | JSON array of Modal Profile objects, each with `name`, `token_id`, `token_secret`, and optional `active`; required for `--modal` |
| `MODAL_CONFIG_PATH` | Optional path to host Modal configuration instead of `~/.modal.toml` |
| `GH_TOKEN`, `GH_ORG_NAME` | GitHub access and default organization for shorthand repository names; writes to GitHub or `config` (`env/`, `caddy/`, `scratchpad/`) need appropriate write access |
| `CLOUDFLARE_TUNNEL_TOKEN` | Credential for an already configured sandbox application tunnel; absent token means startup skips the tunnel |
| `MODAL_SANDBOX_TUNNEL_DOMAIN` | Display hostname for the application tunnel; does not create DNS or configure the tunnel |
| `SSH_AUTHORIZED_KEY` | Bootstrap input populated by the launcher's `sandboxes/shared/ssh-key.pub`; configure the launcher's public-key file to change the key |
| `OPENCODE_GO_API_KEY` | OpenCode provider key used by T3 Code |
| `ANTIGRAVITY_CLIENT_ID`, `ANTIGRAVITY_CLIENT_SECRET`, `ANTIGRAVITY_TOKENS` | Antigravity OAuth configuration and Antigravity account profiles |
| `AGE_PRIVATE_KEY` | Age private key for repository vault decryption; `SOPS_AGE_KEY` is a host resolver fallback, as is `~/.config/sops/age/keys.txt` in vault helpers |
| `DEFAULT_GIT_NAME`, `DEFAULT_GIT_EMAIL` | Fallback sandbox Git authorship; repository-specific authorship comes from `config/env/<repo>/git.env` |
| `DEFAULT_TIMEZONE`, `TZ` | Timezone; factory resolution prefers file values, then host values, then `Asia/Kolkata`; repository vault `TZ` can override the sandbox's selected timezone |
| `MODAL_SANDBOX_ENDPOINT_URL` | Public dashboard endpoint or direct Hosted Sandbox Control Plane origin URL for CLI `--remote` and pool-wide Codex status (e.g. `https://apps.example.com`); `--endpoint-url` overrides it |
| `SANDBOX_DASHBOARD_UPSTREAM` | Optional Hosted Sandbox Control Plane origin URL (`*.modal.run`) used by Caddy apex/CLI route proxying and `modal-sandbox infra dashboard` (auto-discovered via Modal SDK when unset) |
| `SANDBOX_CONTROL_PLANE_URL` | Hosted Sandbox Control Plane origin URL configured in the Next.js Sandbox Web Dashboard and Dashboard Deployer environments (`dashboard/`, `dashboard-deployer/`, `/opt/sandbox-dashboard/.env`, and `/opt/dashboard-deployer/.env`) |
| `NEXT_PUBLIC_DASHBOARD_COMMIT` | Optional short commit badge baked into the Next.js Sandbox Web Dashboard and Dashboard Deployer builds and `/api/health` output by `modal-sandbox infra dashboard` / `deployer` |
| `CODEX_PROFILE_VOLUME_PREFIX` | Opt-in pool of three Codex Credential Profile volumes with `-a`, `-b`, and `-c` suffixes; testing uses a separate prefix |
| `CODEX_STATUS_SECRET` | Signing secret for pool-wide Codex Credential Profile status; configure the same secret on launch host and Hosted Sandbox Control Plane |
| `ALLOW_DIRTY_DEPLOY` | Set to `1` to bypass the Hosted Sandbox Control Plane's clean-working-tree check for development |
| `FACTORY_STATE_DIR` | Override directory for `FactoryStateStore` metadata outside `/root/.factory-state` (`factory-state-v1` volume) |

Pool-wide Codex status also requires an HTTPS `MODAL_SANDBOX_ENDPOINT_URL`. Child sandboxes receive scoped status access rather than the signing secret. See [AI tooling](../guides/ai-tooling.md#codex-credential-profiles).

## Resource Plane clients and deployment

| Variable | Purpose and default |
| :--- | :--- |
| `RESOURCE_PLANE_DOMAIN` | Resource Plane hostname or URL; client fallback `DB_HOST_DOMAIN` |
| `RESOURCE_PLANE_ADMIN_TOKEN` | Client bearer token matching the Resource Plane server's `ADMIN_TOKEN`; fallback `DB_HOST_ADMIN_TOKEN` |
| `RESOURCE_PLANE_SSH_HOST` | Required VPS hostname/IP for deployment |
| `RESOURCE_PLANE_SSH_USER` | Deployment SSH user, default `root` |
| `RESOURCE_PLANE_SSH_PORT` | SSH port, default `22` |
| `RESOURCE_PLANE_SSH_KEY` | Required explicit private key path, normally `.secrets/resource_plane_ssh`; no ambient SSH key fallback (`modal deploy` reads its content into `RESOURCE_PLANE_SSH_PRIVATE_KEY` for Hosted Sandbox Control Plane-backed dashboard self-deploy) |
| `CADDY_STORE_PROFILE` | Host Ingress Proxy configuration profile folder under `caddy/` in the private `config` repository, default `default`; `infra caddy backup`/`restore` and `deploy-app --profile` override it |
| `APPS_BASE_DOMAIN` | Root DNS domain for the apex Sandbox Web Dashboard and Hosted App subdomains, such as `apps.example.com` |
| `CLOUDFLARE_DNS_API_TOKEN` | DNS-01 token for Caddy wildcard certificates, falling back to `CLOUDFLARE_API_TOKEN`; remotely stored in `/opt/caddy/.env` |

`create-db` caches the public root CA at `~/.config/resource-plane/ca.crt`, reusing the legacy `~/.config/db-host` directory when it exists. `--ca-path` selects an explicit path. The generated app supports `RESOURCE_PLANE_CA_CERT` for a portable CA path; `deploy-app` stages the certificate at `/app/.certs/ca.crt` inside its container.

## Resource Plane server variables

These configure the Resource Plane Console, Resource Plane Management API, and persistent services:

| Variable | Purpose |
| :--- | :--- |
| `CONTROL_PLANE_USERNAME`, `CONTROL_PLANE_PASSWORD` | Resource Plane Console Credentials for Basic authentication; `BASIC_AUTH_USERNAME`, `BASIC_AUTH_PASSWORD` take precedence when supplied |
| `ADMIN_TOKEN` | Admin Token for the Resource Plane Management API; `NEON_ADMIN_TOKEN` is a server fallback |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Master Database Credentials for PostgreSQL |
| `SEAWEEDFS_ADMIN_ACCESS_KEY`, `SEAWEEDFS_ADMIN_SECRET_KEY` | Storage Admin Credentials for SeaweedFS |
| `PUBLIC_POSTGRES_HOST` | Hostname/IP used in issued database credentials and certificate SANs |
| `POSTGRES_PORT`, `WEB_PORT`, `S3_PORT` | Production published ports; freshly generated production `.env` uses `5432`, `3000`, `8333` |
| `HOST_BIND_IP` | Published listener address; production default `0.0.0.0`, development Compose default `127.0.0.1` |

Production `resource-plane/deploy.sh` generates `.env` on first use and preserves it thereafter. Local Next.js development resolves its environment in `resource-plane/apps/web/`, with generated credentials written to `.env.local` there. The existing `resource-plane/.env.example` is not a complete production credential template; use the deployment script for first production setup.

## Documentation publishing variables

Both **Dashboard Deployer** (`POST /api/docs/deploy`) and `sandboxes/scripts/deploy-docs.sh` use `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`, plus `APPS_BASE_DOMAIN` (`https://docs.<APPS_BASE_DOMAIN>`) and optional `CLOUDFLARE_PAGES_PROJECT` (default `modal-sandboxes-docs`) and `CLOUDFLARE_PAGES_BRANCH` (default `main`). See [documentation deployment](../guides/deploying-documentation.md).

## Provenance

The launcher records `SOFTWARE_FACTORY_COMMIT`, `SOFTWARE_FACTORY_COMMIT_SHORT`, `SOFTWARE_FACTORY_REF`, and `SOFTWARE_FACTORY_DIRTY`. In a host checkout Git supplies provenance; a deployed Hosted Sandbox Control Plane can propagate its captured provenance. These values identify the factory version that launched the sandbox, independently of the application's own Git history.

## Resolution and propagation

Lookup rules differ between loading factory credentials and sending values to a child sandbox:

| Stage | Resolution |
| :--- | :--- |
| Factory configuration | Root `.env`, then missing keys from legacy `.secrets/.env` and `secrets/.env`; parsed values generally precede host fallbacks |
| Hosted dashboard authentication | Nonempty host `WEB_UI_USERNAME` / `WEB_UI_PASSWORD` precede values from candidate files; both must resolve |
| Hosted Sandbox Control Plane deployment | Parse all root `.env` keys, apply dashboard authentication and Git provenance, then fill missing keys from `CONTROL_PLANE_SECRET_KEYS` in `sandboxes/sandbox/config.py` |
| Child sandbox with root `.env` | Inject that file's values; the explicit `CODEX_STATUS_SECRET` filter excludes the status signing key when present |
| Child sandbox without root `.env` | Forward selected GitHub, Cloudflare, SSH, provider, Age, Modal, dashboard, and Resource Plane environment keys listed in `sandboxes/sandbox/launcher.py` |
| Repository vault | Fetch and decrypt `config/env/<repo>/env.map` and mapped files, then add the repository bundle and Git identity |

The Hosted Sandbox Control Plane's host fallback list also includes Codex Credential Profile and status settings and the remote endpoint URL. The child launcher has a separate fallback list, so these lists must not be treated as interchangeable. An explicit allowlist restricts ambient host fallbacks; it does not restrict all keys in a factory `.env`.

GitHub helpers may additionally resolve `GITHUB_TOKEN` or authenticated `gh` access; Modal Profile management may read `~/.modal.toml`. Scope credentials in the factory `.env` for the sandboxes it will launch. See [credential lifecycle](../architecture/secrets.md) for files created after injection and snapshot implications.
