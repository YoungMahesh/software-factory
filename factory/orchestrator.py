"""Software Factory Orchestrator.

Manages factory job lifecycles, dispatches ephemeral worker sandboxes,
and monitors execution stages.
"""

from typing import TextIO
import sys

from factory.spawner import (
    FACTORY_CPU,
    FACTORY_IDLE_TIMEOUT_SECS,
    FACTORY_STANDARD_MEMORY,
    FACTORY_TIMEOUT_SECS,
    FACTORY_VM_DEFAULT_MEMORY_GB,
    FactorySpawnConfig,
    build_factory_image,
    create_factory_sandbox,
    get_factory_app_name,
    resolve_secrets_dir,
    run_factory_sandbox,
    spawn_factory_sandbox,
    stream_sandbox_logs,
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
    "get_factory_app_name",
    "resolve_secrets_dir",
    "run_factory_sandbox",
    "spawn_factory_sandbox",
    "stream_sandbox_logs",
    "dispatch_job",
]


def dispatch_job(
    project: str,
    feature: str | None = None,
    issue: str | None = None,
    tracker: str | None = None,
    vm: bool = False,
    testing: bool = False,
    model: str | None = None,
    memory_gb: int | None = None,
    timeout_secs: int = FACTORY_TIMEOUT_SECS,
    dev: bool = False,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Dispatches a software factory job into an ephemeral Modal Sandbox.

    Args:
        project: Target project secret name (under secrets/ or software-factory-09-test/ when testing).
        feature: Target feature slug (e.g. 'queues-page') or None when issue is provided.
        issue: Optional specific ticket ID. When None, runs full autonomous batch.
        tracker: Issue tracker provider type ('github' or 'local').
        vm: Whether to run in a full VM Sandbox with Docker support.
        testing: Whether to run against canonical Test Organization under secrets_org/ per ADR 0031.
        model: Optional model override ('deepseek-v4.1-flash' or 'mimo-v2.6-flash').
        memory_gb: Memory allocation in GB (for VM sandboxes).
        timeout_secs: Maximum sandbox runtime in seconds (default 16 hours).
        dev: Whether to launch dev preview keep-alive daemon on port 3000.
        stdout: Standard output stream for live execution logs.
        stderr: Standard error stream for live execution logs.

    Returns:
        The exit code of the in-container pipeline (0 on success).
    """
    effective_feature = feature
    if not effective_feature and issue:
        effective_feature = f"issue-{issue.strip()}"
    if not effective_feature:
        raise ValueError("Either feature or issue must be specified.")

    config = FactorySpawnConfig(
        project=project,
        feature=effective_feature,
        issue=issue,
        tracker=tracker,
        vm=vm,
        testing=testing,
        model=model,
        memory_gb=memory_gb,
        timeout_secs=timeout_secs,
        dev=dev,
    )

    return run_factory_sandbox(config, stdout=stdout, stderr=stderr)
