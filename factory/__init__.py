"""Software Factory core package."""

from factory.orchestrator import (
    FACTORY_CPU,
    FACTORY_IDLE_TIMEOUT_SECS,
    FACTORY_STANDARD_MEMORY,
    FACTORY_TIMEOUT_SECS,
    FACTORY_VM_DEFAULT_MEMORY_GB,
    FactorySpawnConfig,
    build_factory_image,
    create_factory_sandbox,
    dispatch_job,
    get_factory_app_name,
    resolve_secrets_dir,
    run_factory_sandbox,
    spawn_factory_sandbox,
    stream_sandbox_logs,
)
from factory.run import (
    DEFAULT_MODEL,
    SUPPORTED_MODELS,
    main,
    main as run_cli,
    normalize_model_name,
    parse_args,
    validate_project_secrets,
)

__all__ = [
    "FACTORY_CPU",
    "FACTORY_IDLE_TIMEOUT_SECS",
    "FACTORY_STANDARD_MEMORY",
    "FACTORY_TIMEOUT_SECS",
    "FACTORY_VM_DEFAULT_MEMORY_GB",
    "FactorySpawnConfig",
    "build_factory_image",
    "create_factory_sandbox",
    "dispatch_job",
    "get_factory_app_name",
    "resolve_secrets_dir",
    "run_factory_sandbox",
    "spawn_factory_sandbox",
    "stream_sandbox_logs",
    "DEFAULT_MODEL",
    "SUPPORTED_MODELS",
    "main",
    "run_cli",
    "normalize_model_name",
    "parse_args",
    "validate_project_secrets",
]

