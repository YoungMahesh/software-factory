# Deploying Documentation

Modal Sandboxes includes a dedicated serverless documentation application implemented in `sandbox/docs.py`. It builds the MkDocs Material site at container image construction and serves the static files via an unauthenticated ASGI web function on Modal.

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

---

## 2. Local Live Preview (`modal serve`)

To develop and preview documentation changes locally in real time:

```bash
modal serve sandbox/docs.py
```

Modal provisions an ephemeral development container and watches your local filesystem. Any modifications to markdown files in `docs/` or configuration in `mkdocs.yml` automatically bust the image layer cache, re-running `mkdocs build` and updating your live preview URL.

---

## 3. Configuration & Custom Domains

The documentation app runs with zero mandatory configuration. You can optionally bind a custom domain using an environment variable in your root `.env` file:

```env
DOCS_CUSTOM_DOMAIN=docs.yourdomain.com
```

When `DOCS_CUSTOM_DOMAIN` is set, `sandbox/docs.py` automatically binds the domain to the `@modal.asgi_app` endpoint.

---

## 4. Architecture & Scale-to-Zero

- **Independent App**: Deployed under the dedicated Modal App name `modal-sandboxes-docs`, isolating documentation assets and dependencies from the `sandbox-control-plane` provisioning service.
- **Scale-to-Zero (`min_containers=0`)**: The documentation container shuts down when idle, incurring zero compute cost when there is no active traffic. It cold-starts on demand within 1–2 seconds.
- **In-Process ASGI Server**: Powered by Starlette's `StaticFiles(html=True)`, directory routes (such as `/getting-started/`) automatically resolve to `index.html` with clean URLs and proper MIME types.

For further architectural context and design rationale, see [ADR 0101](../adr/0101-publish-documentation-as-modal-web-function.md).
