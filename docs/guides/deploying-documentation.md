# Deploying Documentation

Modal Sandboxes supports dual deployment strategies for its documentation site: an on-demand serverless ASGI web function running on Modal Cloud, and automated static edge deployment to Cloudflare Pages.

The documentation is authored in Markdown within the `docs/` directory and built with the high-performance Rust documentation engine **Zensical** (with fallback to MkDocs).

---

## 1. Quick Deploy to Modal Cloud

Deploy the documentation site directly using the Modal CLI:

```bash
modal deploy sandbox/docs.py
```

Upon successful deployment, Modal outputs the public URL for your documentation application:

```text
✓ Created objects.
├── 🔨 Created docs_web_app => https://<workspace>--docs.modal.run
```

The container image pre-compiles the documentation during image creation and serves compiled assets via Starlette's ASGI static file server.

---

## 2. Deploy to Cloudflare Pages

For globally distributed edge delivery, documentation can be deployed directly to Cloudflare Pages using the bundled automation script:

```bash
./scripts/deploy-docs.sh
```

### Prerequisites & Configuration

The deployment script loads credentials from your root `.env` file (or inherited environment variables). Ensure the following variables are configured in `.env`:

```env
# Cloudflare Pages deployment credentials
CLOUDFLARE_ACCOUNT_ID=your_cloudflare_account_id
CLOUDFLARE_API_TOKEN=your_cloudflare_api_token

# Optional deployment customization
CLOUDFLARE_PAGES_PROJECT=modal-sandboxes-docs
CLOUDFLARE_PAGES_BRANCH=main
```

| Variable | Required | Default | Description |
| :--- | :---: | :--- | :--- |
| `CLOUDFLARE_ACCOUNT_ID` | Yes | — | Your Cloudflare Account ID from the Cloudflare Dashboard. |
| `CLOUDFLARE_API_TOKEN` | Yes | — | Cloudflare API token with `Cloudflare Pages: Edit` permissions. |
| `CLOUDFLARE_PAGES_PROJECT` | No | `modal-sandboxes-docs` | Cloudflare Pages project name. |
| `CLOUDFLARE_PAGES_BRANCH` | No | `main` | Target deployment environment or git branch name. |

### How the Cloudflare Deployment Works

The script (`scripts/deploy-docs.sh`) executes the following automated workflow:

1. **Loads Environment**: Sources variables from `.env` and validates credentials (`CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN`).
2. **Detects Docs Engine**: Auto-detects `zensical` (preferred) or `mkdocs` from your local environment or virtualenv.
3. **Strict Build**: Compiles documentation with `--strict` validation into the `site/` directory, catching any broken internal links or syntax errors.
4. **Edge Deployment via Wrangler**: Uses `wrangler pages deploy site` (falling back to `npx wrangler`) to sync compiled assets directly to Cloudflare Pages.
5. **Live URL Output**: Emits the public deployment URL:
   ```text
   ✅ Documentation successfully built and deployed to Cloudflare Pages!
      Live URL: https://modal-sandboxes-docs.pages.dev
   ```

---

## 3. Local Live Preview

### Modal Remote Live Preview (`modal serve`)

To develop and preview documentation changes in a live ephemeral container on Modal:

```bash
modal serve sandbox/docs.py
```

Modal provisions an ephemeral container and watches your local filesystem. Any modifications to markdown files in `docs/` or configuration in `mkdocs.yml` automatically bust the image layer cache, re-running `zensical build` and updating your live preview URL.

### Local Instant Preview (`zensical serve`)

Alternatively, developers can run Zensical locally with instant hot differential reload:

```bash
zensical serve
```

---

## 4. Configuration & Custom Domains

### Modal Cloud Custom Domains
The Modal documentation app runs with zero mandatory configuration. You can optionally bind a custom domain using an environment variable in your root `.env` file:

```env
DOCS_CUSTOM_DOMAIN=docs.yourdomain.com
```

When `DOCS_CUSTOM_DOMAIN` is set, `sandbox/docs.py` automatically binds the domain to the `@modal.asgi_app` endpoint.

### Cloudflare Pages Custom Domains
To bind a custom domain to your Cloudflare Pages deployment:
1. Open the **Cloudflare Dashboard** -> **Workers & Pages** -> your project (`modal-sandboxes-docs`).
2. Navigate to **Custom domains** -> **Set up a custom domain**.
3. Enter your domain (e.g. `docs.yourdomain.com`) and confirm DNS CNAME record propagation.

---

## 5. Architecture & Comparison

| Feature | Modal Cloud (`sandbox/docs.py`) | Cloudflare Pages (`scripts/deploy-docs.sh`) |
| :--- | :--- | :--- |
| **Serving Model** | Unauthenticated ASGI Web Function on Modal | Static Asset Hosting on Cloudflare Global Edge CDN |
| **Compute / Idle** | Scale-to-zero (`min_containers=0`), idle containers spin down | 100% static edge CDN, zero server container instances |
| **Build Timing** | Built into container image at image construction time | Built locally or in CI with strict validation prior to upload |
| **Cold Starts** | 1–2 seconds when waking from scale-to-zero | Zero cold starts (instant global CDN edge delivery) |
| **Target App / URL** | `https://<workspace>--docs.modal.run` | `https://<project-name>.pages.dev` |

For further architectural context and design rationale, see [ADR 0062](../adr/0062-publish-documentation-as-modal-web-function.md) and [ADR 0068](../adr/0068-migrate-documentation-generator-to-zensical.md).
