# Building and Deploying Documentation

The Markdown site lives in `docs/`, with navigation and extensions configured by `mkdocs.yml`. Local verification uses Zensical. The Cloudflare publishing script can fall back to MkDocs if Zensical is absent.

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

This serves a local development preview. The static build output goes to `site/`. The documentation test builds in strict mode when Zensical is on `PATH`; CI installs the docs extras so this check is exercised. Contract checks cover local links, CLI option references, and registered MCP tool names.

## Publish on Modal

```bash
modal deploy sandboxes/sandbox/docs.py
```

This deploys the separate `modal-sandboxes-docs` app. Its image installs Zensical, builds the staged documentation, and serves static files through FastAPI/Starlette. It does not install docs tooling into development sandboxes. Use the URL reported by Modal after deployment.

For a custom domain, set `DOCS_CUSTOM_DOMAIN` in the **deploying process environment**:

```bash
DOCS_CUSTOM_DOMAIN=docs.example.com modal deploy sandboxes/sandbox/docs.py
```

The docs app reads this value through `os.environ`; it does not load the factory `.env` by itself. Configure the domain using the DNS instructions supplied by Modal. The resulting documentation site is public and has no dashboard Basic authentication.

For a temporary hosted development session:

```bash
modal serve sandboxes/sandbox/docs.py
```

## Publish on Cloudflare Pages

Set the following credentials in the root `.env` or process environment:

```env
CLOUDFLARE_ACCOUNT_ID=your-account-id
CLOUDFLARE_API_TOKEN=your-pages-edit-token
```

Run from the factory checkout:

```bash
./sandboxes/scripts/deploy-docs.sh
```

The script loads the root `.env`, selects a local Zensical or MkDocs executable, builds with `--strict`, and runs Wrangler to upload `site/`. Node.js is needed for the `npx wrangler` fallback when Wrangler is not already installed.

Its default Pages project is `modal-sandboxes-docs`, on branch `main`. Optional project/branch values are read before the script sources `.env`, so export them or supply them to the command:

```bash
CLOUDFLARE_PAGES_PROJECT=my-docs CLOUDFLARE_PAGES_BRANCH=staging \
  ./sandboxes/scripts/deploy-docs.sh
```

Use the deployment URL printed by Wrangler. To add a custom domain, open the Pages project in Cloudflare and configure its custom domain and DNS records.

Publishing is separate from local verification. The [CI workflow](https://github.com/sFactory0/software-factory/blob/main/.github/workflows/docs.yml) builds and checks documentation without publishing it.

Related decisions: [ADR 0062](../adr/0062-publish-documentation-as-modal-web-function.md) and [ADR 0068](../adr/0068-migrate-documentation-generator-to-zensical.md).
