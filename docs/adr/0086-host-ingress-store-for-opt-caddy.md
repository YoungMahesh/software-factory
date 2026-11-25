# Host Ingress Store (`caddy-store`) for `/opt/caddy` Configuration

**Status**: Accepted (Amends [ADR 0085](0085-host-ingress-proxy-in-opt-caddy.md) and [ADR 0057](0057-central-env-store-and-host-side-secret-injection.md))

## Context

[ADR 0085](0085-host-ingress-proxy-in-opt-caddy.md) standardized the **Host Ingress Proxy** as a standalone `/opt/caddy` stack and automated `/opt/caddy/conf/sites/resource-plane.caddy` via `modal-sandbox infra caddy`. On production VPS hosts, however, `/opt/caddy` also accumulates co-located application routes (`/opt/caddy/conf/sites/*.caddy`), customized global ACME options in `/opt/caddy/conf/Caddyfile`, and `/opt/caddy/docker-compose.override.yml` attaching Caddy to co-located external Docker networks.

None of that host-specific configuration was persisted off-VPS. Committing it to `software-factory` would leak private domains, personal ACME emails, and tenant service topology, while placing it inside `env-store` (`software-factory/env.map`) would cause `SandboxLauncher`, `startup.sh`, and `post-checkout` to inject VPS reverse-proxy configs into every Modal sandbox and T3 Git worktree.

## Decision

1. **Dedicated Canonical Private Repository (`caddy-store`)**:
   - Store Host Ingress Proxy configuration in a dedicated private GitHub repository at `github.com/${GH_ORG_NAME}/caddy-store`, strictly decoupled from `env-store`.
   - Keep the repository name strictly canonical (`caddy-store`) with no `CADDY_STORE_REPO` override variable.

2. **Logical Multi-VPS Profile Layout**:
   - Organize stored configurations under logical profile directories inside `caddy-store` (`<profile>/conf/...` and `<profile>/docker-compose.override.yml`), defaulting to `default`.
   - Support `CADDY_STORE_PROFILE` in `.env` and `--profile <name>` CLI overrides so multiple VPS hosts can be managed cleanly and old-to-new VPS migrations preserve configuration across IP changes.

3. **Declarative Scope and Plaintext Storage**:
   - Capture all non-transient declarative files under `/opt/caddy/conf/` (`conf/Caddyfile`, `conf/sites/*.caddy`, and any nested snippets/includes, skipping `.bak`/`.tmp`/`.gitkeep`) alongside `docker-compose.override.yml`.
   - Keep `docker-compose.yml` sourced from `resource-plane/caddy/docker-compose.yml` in Git and exclude `caddy_data`/`caddy_config` Docker volumes (ACME certificates re-issue automatically after DNS cutover).
   - Store files as plaintext inside the private `caddy-store` repository so route and network diffs remain human-readable in Git and Caddy bootstrap does not require `AGE_PRIVATE_KEY`. Inline secrets inside `.caddy` files are prohibited.

4. **Idempotent Direct VPS ↔ `caddy-store` Sync**:
   - Add explicit, idempotent subcommands under `modal-sandbox infra caddy`:
     - `backup`: Mirrors live `/opt/caddy` declarative files from the VPS into `caddy-store/<profile>/`, skipping commits/deletes when unchanged and automatically creating `${GH_ORG_NAME}/caddy-store` as a private repo on `404` when token permissions permit.
     - `restore`: Non-destructively merges `caddy-store/<profile>/` onto the VPS (preserving unstored `.caddy` files unless `--prune` is passed), validates with `caddy validate` with atomic rollback on error, and skips writes/reloads when already converged.
   - Support `--from-store` with `--bootstrap`, opt-in `--sync` on `--domain` updates, and optional `--dir` for local inspection without mandatory `.secrets/caddy/` staging.

5. **Fresh-VPS Network Filtering and Convergence**:
   - Store the full `docker-compose.override.yml` in `caddy-store`, and during `restore` filter applied external networks to those already present on the target VPS (always retaining `dbhost-network` and reporting any skipped networks so re-running `restore` after deploying co-located apps wires them in).
   - Trigger `docker compose up -d` only when `docker-compose.override.yml` changes; apply `conf/`-only changes via zero-downtime `caddy reload`.

6. **Scope Boundary**:
   - Remains strictly scoped to `/opt/caddy`; `/opt/resource-plane/.env` and co-located application Compose stacks stay outside `caddy-store`.

## Considered Options

- **Reuse `env-store` (`software-factory`)**: Rejected because `env-store` is keyed by GitHub repository and `env.map` entries are injected into Modal sandboxes and T3 worktrees.
- **SOPS encryption for `.caddy` and `Caddyfile`**: Rejected because SOPS lacks structured parsers for Caddy configs, wrapping them as opaque blobs and introducing an unnecessary `AGE_PRIVATE_KEY` dependency.
- **Pre-create missing external networks with `docker network create` during `restore`**: Rejected because co-located stacks commonly use Compose-managed networks (`<project>_net`) that fail if pre-created without Compose project labels.

## Consequences

- Rebuilding or migrating a VPS Host Ingress Proxy becomes reproducible, non-destructive, and idempotent without polluting `software-factory` or Modal sandboxes.
- Co-located application stacks can be deployed in any order relative to `/opt/caddy`, converging network attachments on subsequent `restore` invocations.
