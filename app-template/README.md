# App Template

Canonical Next.js 16 web and optional Expo React Native blueprint for Software Factory. It is materialized by `create-app` on a workstation or from `/opt/app-template` inside a sandbox.

```bash
# Full-stack defaults: web, database, authentication, skills, install, and Git.
create-app my-app -y

# Minimal web app without persistence/authentication requirements.
create-app my-demo --no-db --no-auth -y

# Opt-in GitHub + Resource Plane DB + env-store + T3 sandbox.
create-app my-app --cloud -y
```

`apps/web/base` and optional overlays supply the web app. `apps/mobile/base` supplies the mobile client when requested. Shared `packages/theme` and `packages/types` are copied into the generated repository. `skills.json` defines the agent skill allowlist.

This directory is excluded from the factory's pnpm workspace. Run installation, tests, and app commands inside a generated application. Configure `DATABASE_URL` before using database-backed features; credentials and cloud resources are opt-in rather than prerequisites for a minimal web scaffold.

See [application creation and deployment](../docs/guides/applications.md) for local/cloud prerequisites, Hosted App HTTPS, environment handling, and teardown; [CLI reference](../docs/guides/cli.md) for options; and [ADR 0087](../docs/adr/0087-app-template-and-scaffolder-integration.md) for design history.
