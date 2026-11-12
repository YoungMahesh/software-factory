# Publish Documentation as Modal Web Function

**Status**: Accepted

We introduce a dedicated, standalone Modal App (`modal-sandboxes-docs` defined in `sandbox/docs.py`) that builds the repository's MkDocs documentation site during container image construction and serves the resulting static assets via an unauthenticated, serverless ASGI web function with automatic scale-to-zero.

## Context

The repository contains documentation covering architecture, runtimes, ingress, secrets, and architecture decision records built with MkDocs Material (`mkdocs.yml` and `docs/`).

Previously, no dedicated deployment pipeline existed to publish this documentation site to Modal. The existing cloud service in the codebase—the Hosted Sandbox Control Plane (`sandbox/function.py`)—serves the FastAPI control plane API and the Sandbox Web Dashboard SPA under HTTP Basic Authentication. Bundling documentation into the control plane presented several architectural drawbacks:

1. **Route Collisions**: FastAPI by default reserves `/docs` for its interactive OpenAPI Swagger UI. Hosting the project documentation under the same app would require awkward namespace prefixing (e.g., `/documentation` or `/docs/site`).
2. **Image Bloat & Coupling**: Building the documentation requires MkDocs, MkDocs Material, and PyMdown Extensions. Bundling these build tools and the generated HTML files into the control plane image would increase image build times and container footprint for a service responsible for provisioning cloud sandboxes.
3. **Mismatched Authentication Requirements**: The control plane enforces HTTP Basic Authentication to protect sandbox provisioning and credential management. Documentation should be publicly accessible without login.
4. **External Infrastructure Decoupling**: Relying on third-party static hosting platforms (such as GitHub Pages or Vercel) would introduce external CI/CD dependencies when the project itself is a toolkit for running and managing workloads on Modal.

## Decisions

1. **Standalone Modal App (`sandbox/docs.py`)**:
   - Define a dedicated Modal application (`app = modal.App("modal-sandboxes-docs")`) in `sandbox/docs.py`.
   - Decouple the documentation deployment lifecycle from the `sandbox-control-plane` application.

2. **Container Image Build-Time Compilation**:
   - Construct the container image via `modal.Image.debian_slim()`.
   - Install `mkdocs>=1.6.0`, `mkdocs-material>=9.5.0`, `pymdown-extensions>=10.7.0`, and `fastapi>=0.100.0`.
   - Mount `mkdocs.yml` and `docs/` directly as image inputs, followed by `image.run_commands("mkdocs build -f /root/mkdocs.yml -d /root/site")`.
   - Staging source files directly into the image ensures that any local documentation changes during `modal serve sandbox/docs.py` invalidate the layer cache and trigger an automatic rebuild.

3. **In-Process ASGI Static Serving**:
   - Serve static HTML and assets using Starlette's `StaticFiles(directory="/root/site", html=True)` mounted on a clean FastAPI instance without Swagger UI (`docs_url=None`, `redoc_url=None`).
   - Register the handler using `@modal.asgi_app(label="docs", custom_domains=custom_domains)`.
   - `html=True` ensures clean directory URL resolution (e.g., `/getting-started/` maps directly to `/getting-started/index.html`) and proper MIME type handling.

4. **Serverless Scale-to-Zero (`min_containers=0`)**:
   - Configure `@app.function(min_containers=0, timeout=60)` so the web function scales down to zero when idle, incurring zero ongoing compute cost during periods of inactivity.

5. **Public Access & Domain Parameterization**:
   - The documentation web function is unauthenticated, allowing public access.
   - Sets `label="docs"` yielding predictable URLs (`https://<workspace>--docs.modal.run`), with optional custom domain routing configured via `DOCS_CUSTOM_DOMAIN`.

## Consequences

- Documentation can be deployed to Modal with a single command: `modal deploy sandbox/docs.py`.
- Developers can run live previews locally with `modal serve sandbox/docs.py`.
- Control plane image dependencies and security boundaries remain completely clean.
- All new files comply with the Universal File Line Budget (ADR 0057 / AGENTS.md).
