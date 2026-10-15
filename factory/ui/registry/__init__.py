"""In-Memory Job Registry and Assembly Line Stage Detector.

Re-exports all public functions, classes, enums, and singleton instances for full backward compatibility.
"""

from factory.spawner import create_factory_sandbox, create_preview_sandbox
from factory.ui.github import (
    fetch_repo_issues,
    fetch_repo_milestones,
    fetch_repo_scratch_metadata,
)
from factory.ui.registry._dispatch import JobRegistry, job_registry
from factory.ui.registry._milestones import (
    PREVIEW_COMPILATION_ERROR_PATTERN,
    PREVIEW_STAGE_PATTERNS,
    STAGE_PATTERNS,
)
from factory.ui.registry._models import (
    DEFAULT_PREVIEW_URL,
    FactoryJob,
    JobStage,
    JobStatus,
    PREVIEW_STAGE_ORDER,
    PreviewStage,
    PreviewState,
    PreviewStatus,
)
from factory.ui.registry._preview import (
    PreviewRegistry,
    preview_registry,
    resolve_active_preview_branch,
)

__all__ = [
    "DEFAULT_PREVIEW_URL",
    "FactoryJob",
    "JobRegistry",
    "JobStage",
    "JobStatus",
    "PREVIEW_COMPILATION_ERROR_PATTERN",
    "PREVIEW_STAGE_ORDER",
    "PREVIEW_STAGE_PATTERNS",
    "PreviewRegistry",
    "PreviewStage",
    "PreviewState",
    "PreviewStatus",
    "STAGE_PATTERNS",
    "create_factory_sandbox",
    "create_preview_sandbox",
    "fetch_repo_issues",
    "fetch_repo_milestones",
    "fetch_repo_scratch_metadata",
    "job_registry",
    "preview_registry",
    "resolve_active_preview_branch",
]
