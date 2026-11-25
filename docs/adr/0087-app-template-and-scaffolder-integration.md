# App Template and Python App Scaffolder Integration

**Status**: Accepted (Amends [ADR 0081](0081-monorepo-architecture-for-execution-and-resource-planes.md)).

## Context

New web and mobile applications in the factory were previously scaffolded from an external repository (`sFactory0/base-template` / `~/base-template`) containing a standalone TypeScript CLI (`create-base-app`) and template directories. Keeping the starter template outside `software-factory` caused three recurring points of friction:

1. **Repository & Skill Drift**: Updates to Matt Pocock's `.agents/skills/` and `@repo/theme` tokens in `software-factory` drifted out of sync with the external template repo, while `resource-plane/` itself originated from that template (Resource Plane ADR 0021).
2. **Disconnected Cloud Provisioning**: Generating a new app required separate manual steps to create a GitHub repository, provision a Resource Plane PostgreSQL database (`create-db`) or SeaweedFS S3 bucket (`create-s3`), push `.env` secrets to `env-store` (`push-repo-env`), and launch a Modal Sandbox (`modal-sandbox --t3`).
3. **Host-to-Sandbox TLS & Monorepo `.env` Friction**: Scaffolded apps placed `.env` at the monorepo root (unloaded by `apps/web` working-directory commands on developer workstations) and `create-db` wrote workstation-specific `sslrootcert` paths into `DATABASE_URL` that failed inside fresh Modal sandboxes.

## Decision

### 1. Monorepo Absorption Under Top-Level `app-template/`
- Absorb the starter application blueprint directly into `software-factory` at top-level `app-template/` (parallel to `sandboxes/` and `resource-plane/`), keeping `app-template/**` outside root `pnpm-workspace.yaml` so template placeholder manifests do not affect monorepo workspace resolution.
- Stage `app-template/` into `/opt/app-template` in the `Shared Base Image` (`sandboxes/shared/image.py`) and hosted control plane image (`sandboxes/sandbox/function.py`) so `create-app` works identically on developer workstations and inside any Modal sandbox.

### 2. Unified Python App Scaffolder (`create-app`)
- Port the scaffolding engine from TypeScript (`src/*.ts` + `dist/`) into Python under `sandboxes/sandbox/app_scaffolder/` and `sandboxes/scripts/create_app.py`, exposed as `create-app` in `pyproject.toml` and `modal-sandbox create-app`.
- Eliminating the separate `tsc` build step allows `create-app` to obey the universal Python line budget and `pytest` harness while importing `create_database_connection`, `create_s3_bucket`, `push_repo_env`, and `launch_sandbox` directly in-process.
- Preserve existing template flags (`--mobile-app`, `--db` for Drizzle ORM, `--auth`, `--skills`, `--install`, `--git`, `-y`) and introduce distinct cloud automation flags (`--github`, `--public`, `--provision-db`, `--provision-s3`, `--push-vault`, `--launch`, `--cloud`) to avoid colliding with `--db`.
- Support scaffolding into empty directories and fresh Standalone Sandbox workspaces (`.git` + `.gitignore` only, merging `.gitignore` and reusing `.git`) while requiring `--force` for non-empty directories.

### 3. Explicit Skills Allowlist & Single Source of Truth
- Maintain `app-template/skills.json` declaring the explicit allowlist of skill names, expected `source` (`mattpocock/skills`), and pinned `commit` SHA.
- Copy allowlisted skill directories and `docs/agents/` directly from `software-factory`'s root `.agents/skills/` and `docs/agents/` (staged into `/opt/app-template/_skills_source` for in-sandbox use), writing a filtered `skills-lock.json` containing only the allowlisted skills plus starter `AGENTS.md` and `GLOSSARY.md`.
- Factory-specific and future custom non-Matt-Pocock skills in `.agents/skills/` (such as `modal` and `close-modal-sandboxes`) are never propagated to scaffolded apps unless explicitly added to `app-template/skills.json`.

### 4. Decoupled Template Packages with Parity Verification
- Keep `app-template/packages/theme` and `app-template/packages/types` separate from `resource-plane/packages/{theme,types}` so `resource-plane/Dockerfile` retains its self-contained Docker build context and NodeNext `.js` imports.
- Enforce `@repo/theme` design token parity (`colors.ts`, `radii.ts`, `spacing.ts`, `typography.ts`) between both subsystems via automated tests.

### 5. Portable TLS CA Resolution & Workspace `.env` Loading
- Keep a single root `.env` compatible with `push-repo-env` and Git worktree `post-checkout` propagation, and load `../../.env` in `apps/web/lib/env.ts` from `next.config.ts`, `drizzle.config.ts`, and `lib/auth.ts`.
- Resolve missing `sslrootcert` paths dynamically in `apps/web/db/config.ts` across `~/.config/resource-plane/ca.crt`, `~/.config/db-host/ca.crt`, and local `.certs/ca.crt` fallbacks, while `sandboxes/shared/startup.sh` automatically caches `/api/ca.crt` into `/root/.config/resource-plane/ca.crt` when `RESOURCE_PLANE_DOMAIN` is configured.
- Parameterize mobile `app.json` identifiers (`scheme`, `ios.bundleIdentifier`, `android.package`) and `serve-apk.js` metadata from `projectName`, and generate a random `BETTER_AUTH_SECRET` on scaffold.

## Consequences

- **One-Command Cloud App Creation**: Developers and agents can go from zero to a pushed GitHub repository, provisioned PostgreSQL DB, encrypted `env-store` secrets, and live T3 Code sandbox in a single `create-app my-app --cloud` invocation, or scaffold locally inside any Standalone Sandbox with `create-app .`.
- **Zero Custom-Skill Leakage**: Custom skills added to `software-factory` remain isolated from generated apps while keeping Matt Pocock skills deduplicated in git.
- **Standalone Repo Retirement**: `software-factory` becomes the canonical source of truth for the App Template, enabling `sFactory0/base-template` to be retired.
