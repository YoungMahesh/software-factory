# Migrate Documentation Generator to Zensical

**Status**: Accepted (Amends [ADR 0062](0062-publish-documentation-as-modal-web-function.md))

We adopt [Zensical](https://zensical.org/) as the primary documentation compiler and preview runner for the repository's static documentation site, preserving full compatibility with `mkdocs.yml` while addressing the announced End of Life (EOL) for Material for MkDocs on May 5, 2027.

## Context

The repository contains extensive documentation covering architecture, runtimes, ingress, secrets, and architecture decision records (ADRs). In [ADR 0062](0062-publish-documentation-as-modal-web-function.md), we established a dedicated Modal Web Function application (`sandbox/docs.py`) to build and serve static documentation via an unauthenticated ASGI web service with scale-to-zero compute.

During a documentation build audit, the Material for MkDocs CLI reported its impending deprecation and end-of-life date:
```text
Material for MkDocs reaches end of life on May 5, 2027.
Critical fixes and security updates continue until that date.

Zensical is its maintained successor, built by the same team.
Try it alongside MkDocs with your existing mkdocs.yml:
https://zensical.org/docs/compatibility/mkdocs/migration/
```

Material for MkDocs relies on Python-Markdown and Jinja2, which exhibit slower build times (~4–8s) as documentation and ADR count expand past 67+ records. Zensical is built with a Rust core and MiniJinja, delivering instant differential rebuilding (verified sub-second builds at ~0.35s–0.64s for this repository) and native reimplementations of search and markdown extensions.

Because Zensical natively parses `mkdocs.yml`, projects do not require immediate conversion to `zensical.toml` and can adopt the new engine gradually and reversibly without breaking existing workflows or deployment pipelines.

## Decisions

1. **Adopt Zensical as Documentation Engine**:
   - Add `zensical>=0.1.1` to optional project dependencies under `[project.optional-dependencies.docs]` in `pyproject.toml`.
   - Maintain `mkdocs` and `mkdocs-material` as complementary dependencies during the dual-runner transition period to preserve zero-friction rollbacks.

2. **Preserve `mkdocs.yml` Single Source of Truth**:
   - Retain `mkdocs.yml` as the single configuration file for site metadata, navigation trees, palettes, and markdown extensions.
   - Both `zensical build` and `mkdocs build` continue to work against this configuration.

3. **Update Modal Documentation Container Image (`sandbox/docs.py`)**:
   - In `sandbox/docs.py`, update `docs_image` to install `zensical>=0.1.1` alongside `fastapi>=0.100.0`.
   - Compile documentation at container image build time via `zensical build -f /root/mkdocs.yml`.
   - Generated assets continue to output to `/root/site` (respecting `site_dir: site`), seamlessly served by the existing `FastAPI` / `StaticFiles(directory="/root/site", html=True)` ASGI handler.

4. **Update Cloudflare Deployment Script (`scripts/deploy-docs.sh`)**:
   - Update `scripts/deploy-docs.sh` to dynamically resolve the documentation compiler binary, giving precedence to `zensical` before falling back to `mkdocs`.
   - Execute strict compilation via `"${DOCS_BUILDER}" build --strict`.

5. **Automated Verification in Test Suite (`tests/test_docs.py`)**:
   - Extend `tests/test_docs.py` with `test_zensical_build_clean` to enforce that `zensical build --strict` executes with exit code 0 and zero warnings.

6. **Developer Workflows and CLI Guidance**:
   - Update `readme.md` and `docs/guides/deploying-documentation.md` to recommend `zensical serve` for local hot-reload preview and `zensical build --strict` for static site verification.

## Consequences

- **Sub-Second Build Performance**: Documentation compile time is reduced by ~7.5x (from ~4.8s down to ~0.35s–0.64s), accelerating container image builds on Modal and Cloudflare Pages deployments.
- **Future-Proofed Maintenance**: Eliminates dependency on Material for MkDocs ahead of its May 5, 2027 EOL.
- **Reversible & Zero Disruption**: Existing configuration syntax, directory structures (`docs/`, `site/`), ADR indices, and search indexing remain completely compatible without requiring any markdown file conversions.
- **Budget Compliance**: All modified Python modules remain strictly within the Universal File Line Budget (<= 500 lines per ADR 0027).
