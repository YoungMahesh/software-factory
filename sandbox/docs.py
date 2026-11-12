"""Modal Web Function application serving the compiled MkDocs documentation site."""

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import modal

logger = logging.getLogger(__name__)

APP_NAME = "modal-sandboxes-docs"
app = modal.App(APP_NAME)

repo_root = Path(__file__).resolve().parent.parent

# Modal Image with MkDocs build dependencies and staged documentation sources
# Note: copy=True is required on add_local_* when subsequent build commands (e.g. run_commands) are executed
docs_image = (
    modal.Image.debian_slim()
    .pip_install(
        "mkdocs>=1.6.0",
        "mkdocs-material>=9.5.0",
        "pymdown-extensions>=10.7.0",
        "fastapi>=0.100.0",
    )
    .add_local_file(str(repo_root / "mkdocs.yml"), "/root/mkdocs.yml", copy=True)
    .add_local_dir(str(repo_root / "docs"), "/root/docs", copy=True)
    .run_commands("mkdocs build -f /root/mkdocs.yml -d /root/site")
)


def create_docs_app(site_dir: Path | str = "/root/site") -> FastAPI:
    """Creates a FastAPI ASGI application that mounts and serves the static docs directory."""
    docs_fastapi = FastAPI(
        title="Modal Sandboxes Documentation",
        description="Static documentation site for Modal Sandboxes and Software Factory.",
        version="1.0.0",
        docs_url=None,
        redoc_url=None,
    )

    site_path = Path(site_dir)
    if site_path.is_dir():
        docs_fastapi.mount(
            "/",
            StaticFiles(directory=str(site_path), html=True),
            name="site",
        )
    else:
        logger.warning("Docs site directory %s not found. Mount skipped.", site_path)

    return docs_fastapi


custom_domain = os.environ.get("DOCS_CUSTOM_DOMAIN")
custom_domains = [custom_domain] if custom_domain else None


@app.function(
    image=docs_image,
    min_containers=0,
    timeout=60,
)
@modal.asgi_app(label="docs", custom_domains=custom_domains)
def docs_web_app():
    """ASGI entrypoint for Modal Web Function serving static documentation."""
    return create_docs_app("/root/site")
