# Building and Deploying Documentation

The Markdown site lives in `docs/`, with navigation and extensions configured by `mkdocs.yml`. Local verification uses Zensical. The **Documentation Web App** is hosted exclusively on Cloudflare Pages at `https://docs.<APPS_BASE_DOMAIN>`.

## Install and verify locally

From the factory checkout and its active Python environment:

```bash
python -m pip install -r requirements.txt
zensical build --strict
pytest sandboxes/tests/test_docs.py sandboxes/tests/test_documentation_contracts.py
```

The requirements select `.[dev,docs]`, including pytest, Zensical, MkDocs Material, and Markdown extensions. Fresh Software Factory repository sandboxes with Modal tooling enabled install these requirements automatically. Snapshot resumption skips dependency installation, so update requirements manually in an existing or resumed sandbox when needed.

```bash
zensical serve
```

This serves a local development preview. The static build output goes to `site/`. The documentation test builds in strict mode when Zensical is on `PATH`; the manually dispatched CI workflow installs the docs extras so this check is exercised. Contract checks cover local links, CLI option references, registered MCP tool names, ADR indexing, and Hosted Sandbox Control Plane API routes.

## One-time Cloudflare Pages & DNS Setup

Set the following values in the root `.env` (or environment) and redeploy the **Hosted Sandbox Control Plane** (`modal deploy sandboxes/sandbox/function.py`):

```env
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_API_TOKEN=your-pages-edit-token
APPS_BASE_DOMAIN=apps.example.com
```

Because `*.<APPS_BASE_DOMAIN>` routes to the VPS Host Ingress Proxy, wire `https://docs.<APPS_BASE_DOMAIN>` once in Cloudflare:

1. Create or open the Cloudflare Pages project (`CLOUDFLARE_PAGES_PROJECT`, defaulting to `modal-sandboxes-docs`, production branch `main`).
2. Attach `docs.<APPS_BASE_DOMAIN>` as a Custom Domain on that Cloudflare Pages project.
3. Ensure an explicit `CNAME` record for `docs.<APPS_BASE_DOMAIN>` points to the Cloudflare Pages target (`<project>.pages.dev`) so Cloudflare handles `docs.<APPS_BASE_DOMAIN>` directly rather than falling through to the VPS wildcard record.

## Deploy via Dashboard Deployer

Open **Dashboard Deployer** (`https://deploy.<APPS_BASE_DOMAIN>`) and click **Deploy Documentation Web App**.

The **Hosted Sandbox Control Plane** (`POST /api/docs/deploy`) spawns `run_docs_deploy` in a dedicated `docs_deploy_image` container, clones `main` from GitHub, runs `zensical build --strict`, writes `/deploy-info.json` (`commit`, `commit_short`, `deployed_at`) into `site/`, and uploads `site/` to Cloudflare Pages via Wrangler. **Dashboard Deployer** polls deployment logs independently of **Sandbox Web Dashboard** deploys and displays the live deployed commit from `https://docs.<APPS_BASE_DOMAIN>/deploy-info.json`.

## Manual CLI Deployment on Cloudflare Pages

You can also build and upload `site/` directly from a local factory checkout:

```bash
./sandboxes/scripts/deploy-docs.sh
```

The script loads the root `.env`, selects a local Zensical or MkDocs executable, builds with `--strict`, writes `site/deploy-info.json`, and runs Wrangler to upload `site/`. Node.js is needed for the `npx wrangler` fallback when Wrangler is not already installed.

Its default Pages project is `modal-sandboxes-docs`, on branch `main`. Optional project/branch values are read before the script sources `.env`, so export them or supply them to the command:

```bash
CLOUDFLARE_PAGES_PROJECT=my-docs CLOUDFLARE_PAGES_BRANCH=staging \
  ./sandboxes/scripts/deploy-docs.sh
```

Publishing is separate from local verification. The manually dispatched (`workflow_dispatch`) [CI workflow](https://github.com/YoungMahesh/software-factory/blob/main/.github/workflows/docs.yml) builds and checks documentation without publishing it.

Related decisions: [ADR 0068](../adr/0068-migrate-documentation-generator-to-zensical.md) and [ADR 0100](../adr/0100-cloudflare-documentation-deployer-and-modal-docs-retirement.md).
