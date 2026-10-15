"""Modal Factory Sandbox Spawner and Provisioning Engine.

Provisions ephemeral Modal Sandboxes (Standard Sandboxes with burstable memory
by default, or VM Sandboxes when virtualization is requested) running the
assembly line pipeline with mounted factory harness and scoped credentials.
"""

from factory.spawner._config import (
    DEFAULT_TEST_ORG,
    FACTORY_CPU,
    FACTORY_IDLE_TIMEOUT_SECS,
    FACTORY_STANDARD_MEMORY,
    FACTORY_TIMEOUT_SECS,
    FACTORY_VM_DEFAULT_MEMORY_GB,
    PREVIEW_ALLOWED_HOSTS,
    PREVIEW_IDLE_TIMEOUT_SECS,
    PREVIEW_PORT,
    FactorySpawnConfig,
    PreviewSpawnConfig,
    build_factory_image,
    get_factory_app_name,
    normalize_project_name,
    resolve_repo_root,
    resolve_secrets_dir,
    resolve_target_repo,
)
from factory.spawner._factory import (
    create_factory_sandbox,
    run_factory_sandbox,
    spawn_factory_sandbox,
    stream_sandbox_logs,
)
from factory.spawner._preview import (
    create_preview_sandbox,
    spawn_preview_sandbox,
)

__all__ = [
    "DEFAULT_TEST_ORG",
    "FACTORY_CPU",
    "FACTORY_IDLE_TIMEOUT_SECS",
    "FACTORY_STANDARD_MEMORY",
    "FACTORY_TIMEOUT_SECS",
    "FACTORY_VM_DEFAULT_MEMORY_GB",
    "PREVIEW_ALLOWED_HOSTS",
    "PREVIEW_IDLE_TIMEOUT_SECS",
    "PREVIEW_PORT",
    "FactorySpawnConfig",
    "PreviewSpawnConfig",
    "build_factory_image",
    "get_factory_app_name",
    "normalize_project_name",
    "resolve_repo_root",
    "resolve_secrets_dir",
    "resolve_target_repo",
    "create_factory_sandbox",
    "run_factory_sandbox",
    "spawn_factory_sandbox",
    "stream_sandbox_logs",
    "create_preview_sandbox",
    "spawn_preview_sandbox",
]
