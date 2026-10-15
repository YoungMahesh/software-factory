"""Factory sandbox provisioning and execution streaming."""

from pathlib import Path
import sys
import threading
from typing import Any, TextIO

import modal

from shared.image import (
    REMOTE_FACTORY_ENTRYPOINT,
    SHARED_SECRET_NAME,
)
from factory.spawner._config import (
    FACTORY_CPU,
    FACTORY_STANDARD_MEMORY,
    FACTORY_VM_DEFAULT_MEMORY_GB,
    PREVIEW_ALLOWED_HOSTS,
    FactorySpawnConfig,
    build_factory_image,
    get_factory_app_name,
    resolve_repo_root,
    resolve_secrets_dir,
    resolve_target_repo,
)


def create_factory_sandbox(config: FactorySpawnConfig) -> modal.Sandbox:
    """Creates and launches an ephemeral Modal sandbox for a factory job.

    Args:
        config: FactorySpawnConfig describing the job parameters.

    Returns:
        The running modal.Sandbox instance.
    """
    root = resolve_repo_root(config.repo_root)
    secrets_dir = resolve_secrets_dir(
        project=config.project,
        testing=config.testing,
        repo_root=root,
    )
    factory_dir = root / "sandbox" / "factory"

    app_name = config.app_name or get_factory_app_name(
        project=config.project,
        testing=config.testing,
    )
    app = modal.App.lookup(app_name, create_if_missing=True)

    image = build_factory_image(
        project_secrets_dir=secrets_dir,
        factory_dir=factory_dir,
        repo_root=root,
        install_deps=config.install_deps,
    )

    target_repo = resolve_target_repo(config.project, testing=config.testing)

    feature_slug = config.feature
    if not feature_slug and config.issue:
        feature_slug = f"issue-{config.issue.strip()}"

    effective_tracker = config.tracker
    if not effective_tracker and (config.testing or target_repo or (secrets_dir / "token").is_file()):
        effective_tracker = "github"

    env: dict[str, str | None] = {
        "APP_NAME": app_name,
        "FEATURE_SLUG": feature_slug,
        "ENABLE_CLOUDFLARE": "1" if config.dev else "0",
        "ENABLE_DOCKER": "1" if config.vm else "0",
    }
    if config.dev:
        env["DEV_PREVIEW"] = "1"
        env["PORT"] = "3000"
        env["__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS"] = PREVIEW_ALLOWED_HOSTS
    if effective_tracker:
        env["TRACKER"] = effective_tracker
    if target_repo:
        env["GH_REPO"] = target_repo

    sandbox_kwargs: dict[str, Any] = {
        "timeout": config.timeout_secs,
        "idle_timeout": config.idle_timeout_secs,
        "image": image,
        "app": app,
        "cpu": FACTORY_CPU,
        "secrets": [modal.Secret.from_name(SHARED_SECRET_NAME)],
        "env": env,
    }

    if config.vm:
        memory_gb = (
            config.memory_gb
            if config.memory_gb is not None
            else FACTORY_VM_DEFAULT_MEMORY_GB
        )
        sandbox_kwargs["memory"] = memory_gb * 1024
        sandbox_kwargs["experimental_options"] = {"vm_runtime": True}
        env["SWAP_GB"] = str(memory_gb * 2)
    else:
        sandbox_kwargs["memory"] = FACTORY_STANDARD_MEMORY

    # Build entrypoint invocation
    entrypoint_args: list[str] = [
        "bash",
        REMOTE_FACTORY_ENTRYPOINT,
        "--feature",
        feature_slug,
    ]
    if config.issue:
        entrypoint_args.extend(["--issue", config.issue])
    if config.model:
        entrypoint_args.extend(["--model", config.model])
    if config.tracker:
        entrypoint_args.extend(["--tracker", config.tracker])
    if config.dev:
        entrypoint_args.append("--dev")

    with modal.enable_output():
        sandbox = modal.Sandbox.create(
            *entrypoint_args,
            **sandbox_kwargs,
        )

    return sandbox


def spawn_factory_sandbox(config: FactorySpawnConfig) -> modal.Sandbox:
    """Convenience alias for create_factory_sandbox."""
    import factory.spawner

    return factory.spawner.create_factory_sandbox(config)


def stream_sandbox_logs(
    sandbox: modal.Sandbox,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Streams live stdout and stderr from a running sandbox until completion.

    Args:
        sandbox: The active modal.Sandbox instance.
        stdout: Destination stream for stdout lines.
        stderr: Destination stream for stderr lines.

    Returns:
        The exit code of the sandbox process (0 on success).
    """
    def _read_stream(stream: Any, destination: TextIO) -> None:
        try:
            for line in stream:
                destination.write(line)
                destination.flush()
        except Exception:
            pass

    t_stdout = threading.Thread(target=_read_stream, args=(sandbox.stdout, stdout))
    t_stderr = threading.Thread(target=_read_stream, args=(sandbox.stderr, stderr))

    t_stdout.start()
    t_stderr.start()

    try:
        sandbox.wait(raise_on_termination=False)
    except Exception:
        pass

    t_stdout.join(timeout=15.0)
    t_stderr.join(timeout=15.0)

    return sandbox.returncode if sandbox.returncode is not None else 0


def run_factory_sandbox(
    config: FactorySpawnConfig,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Provisions a factory sandbox, streams live execution logs, and returns exit code.

    Args:
        config: FactorySpawnConfig describing the job.
        stdout: Destination stream for stdout.
        stderr: Destination stream for stderr.

    Returns:
        The process exit code.
    """
    import factory.spawner

    sandbox = factory.spawner.create_factory_sandbox(config)
    return factory.spawner.stream_sandbox_logs(sandbox, stdout=stdout, stderr=stderr)

