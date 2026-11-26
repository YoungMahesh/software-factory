"""First-party App Scaffolder package for materializing the App Template blueprint."""

from __future__ import annotations

from typing import Any

from sandbox.app_scaffolder._template import (
    AppScaffoldRequest,
    AppScaffoldResult,
    CloudWiringOptions,
    load_skills_manifest,
    resolve_app_template_dir,
    resolve_skills_source_dir,
    sanitize_identifiers,
    scaffold_app,
)

_CLOUD_EXPORTS = frozenset({
    "CloudWiringResult",
    "ensure_github_repo_and_push",
    "wire_cloud_resources",
})


def __getattr__(name: str) -> Any:
    if name in _CLOUD_EXPORTS:
        from sandbox.app_scaffolder import _cloud

        return getattr(_cloud, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "AppScaffoldRequest",
    "AppScaffoldResult",
    "CloudWiringOptions",
    "CloudWiringResult",
    "ensure_github_repo_and_push",
    "load_skills_manifest",
    "resolve_app_template_dir",
    "resolve_skills_source_dir",
    "sanitize_identifiers",
    "scaffold_app",
    "wire_cloud_resources",
]
