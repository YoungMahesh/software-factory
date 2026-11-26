"""Modal image staging helpers for App Template and Sandbox runtime scripts."""

from __future__ import annotations

import json
from pathlib import Path
import modal


def stage_app_template_into_image(
    image: modal.Image,
    template_dir: Path | None = None,
    factory_root: Path | None = None,
    *,
    copy: bool = True,
    remote_app_template_dir: str = "/opt/app-template",
) -> modal.Image:
    """Bakes App Template files and allowlisted Matt Pocock skills into /opt/app-template."""
    repo_root = Path(__file__).resolve().parent.parent
    default_dir = repo_root.parent / "app-template"
    tmpl_dir = template_dir or (default_dir if default_dir.is_dir() else Path(remote_app_template_dir))
    if not (tmpl_dir / "base").is_dir():
        return image

    image = image.add_local_dir(
        tmpl_dir,
        remote_app_template_dir,
        copy=copy,
        ignore=["node_modules", "**/node_modules", ".next", "**/.next", "_skills_source"],
    )

    pre_staged = tmpl_dir / "_skills_source"
    src_root = pre_staged if (pre_staged / ".agents" / "skills").is_dir() else (factory_root or tmpl_dir.parent)
    manifest_file = tmpl_dir / "skills.json"
    skills_dir = src_root / ".agents" / "skills"
    lock_file = src_root / "skills-lock.json"
    if manifest_file.is_file() and skills_dir.is_dir() and lock_file.is_file():
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        allowlisted = [s for s in manifest.get("skills", []) if (skills_dir / s).is_dir()]
        if allowlisted:
            patterns = [p for name in allowlisted for p in (name, f"{name}/**")]
            image = image.add_local_dir(
                skills_dir,
                f"{remote_app_template_dir}/_skills_source/.agents/skills",
                copy=copy,
                ignore=~modal.FilePatternMatcher(*patterns),
            )
        image = image.add_local_file(
            lock_file, f"{remote_app_template_dir}/_skills_source/skills-lock.json", copy=copy
        )
        agent_docs_dir = src_root / "docs" / "agents"
        if agent_docs_dir.is_dir():
            image = image.add_local_dir(
                agent_docs_dir,
                f"{remote_app_template_dir}/_skills_source/docs/agents",
                copy=copy,
            )
    return image


def stage_sandbox_runtime_into_image(
    image: modal.Image,
    sandbox_pkg_dir: Path | None = None,
    shared_pkg_dir: Path | None = None,
    *,
    copy: bool = True,
    remote_sandbox_runtime_dir: str = "/opt/sandboxes/sandbox",
    remote_shared_runtime_dir: str = "/opt/sandboxes/shared",
) -> modal.Image:
    """Stages sandboxes/sandbox and sandboxes/shared into /opt/sandboxes on Python site-packages."""
    sandboxes_root = Path(__file__).resolve().parent.parent
    pkg_dir = sandbox_pkg_dir
    if pkg_dir is None:
        candidate = sandboxes_root / "sandbox"
        if (candidate / "__init__.py").is_file():
            pkg_dir = candidate
        else:
            try:
                import sandbox as _sandbox_pkg

                pkg_dir = Path(_sandbox_pkg.__file__).resolve().parent
            except Exception:
                pkg_dir = candidate

    shared_dir = shared_pkg_dir
    if shared_dir is None:
        candidate_shared = sandboxes_root / "shared"
        shared_dir = candidate_shared if (candidate_shared / "image.py").is_file() else Path(__file__).resolve().parent

    staged_any = False
    if pkg_dir.is_dir():
        image = image.add_local_dir(
            pkg_dir,
            remote_sandbox_runtime_dir,
            copy=copy,
            ignore=["__pycache__", "**/__pycache__"],
        )
        staged_any = True
    if shared_dir.is_dir():
        image = image.add_local_dir(
            shared_dir,
            remote_shared_runtime_dir,
            copy=copy,
            ignore=["__pycache__", "**/__pycache__"],
        )
        staged_any = True
    if copy and staged_any:
        image = image.run_commands(
            "python3 -c \"import pathlib, site; pathlib.Path(site.getsitepackages()[0], 'software_factory.pth').write_text('/opt/sandboxes\\n')\""
        )
    return image
