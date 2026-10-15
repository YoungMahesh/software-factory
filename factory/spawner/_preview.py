"""Dedicated Preview Sandbox spawner and tunnel resolution."""

from typing import Any
import modal

from shared.image import (
    REMOTE_FACTORY_ENTRYPOINT,
    SHARED_SECRET_NAME,
)
from factory.spawner._config import (
    FACTORY_CPU,
    FACTORY_STANDARD_MEMORY,
    PREVIEW_ALLOWED_HOSTS,
    PREVIEW_PORT,
    PreviewSpawnConfig,
    build_factory_image,
    get_factory_app_name,
    resolve_repo_root,
    resolve_secrets_dir,
    resolve_target_repo,
)


def create_preview_sandbox(config: PreviewSpawnConfig) -> tuple[modal.Sandbox, str]:
    """Creates and launches an ephemeral Modal Dedicated Preview Sandbox.

    Configured with encrypted_ports=[3000], ENABLE_CLOUDFLARE=0, and a 30-minute idle timeout.
    Bypasses agent stages (Planner, Coder, Verifier, Reviewer) and captures the unique
    Modal Application Tunnel URL on port 3000.
    """
    root = resolve_repo_root(config.repo_root)
    secrets_dir = resolve_secrets_dir(
        project=config.repo,
        testing=config.testing,
        repo_root=root,
    )
    factory_dir = root / "sandbox" / "factory"

    app_name = config.app_name or get_factory_app_name(
        project=config.repo,
        testing=config.testing,
    )
    app = modal.App.lookup(app_name, create_if_missing=True)

    image = build_factory_image(
        project_secrets_dir=secrets_dir,
        factory_dir=factory_dir,
        repo_root=root,
        install_deps=config.install_deps,
    )

    target_repo = resolve_target_repo(config.repo, testing=config.testing) or config.repo

    env: dict[str, str | None] = {
        "APP_NAME": app_name,
        "GH_REPO": target_repo,
        "BRANCH": config.branch,
        "ENABLE_CLOUDFLARE": "0",
        "ENABLE_DOCKER": "0",
        "DEV_PREVIEW": "1",
        "PORT": str(PREVIEW_PORT),
        "__VITE_ADDITIONAL_SERVER_ALLOWED_HOSTS": PREVIEW_ALLOWED_HOSTS,
    }

    entrypoint_args: list[str] = [
        "bash",
        REMOTE_FACTORY_ENTRYPOINT,
        "--preview-only",
        "--branch",
        config.branch,
    ]

    sandbox_kwargs: dict[str, Any] = {
        "timeout": config.timeout_secs,
        "idle_timeout": config.idle_timeout_secs,
        "image": image,
        "app": app,
        "cpu": FACTORY_CPU,
        "memory": FACTORY_STANDARD_MEMORY,
        "secrets": [modal.Secret.from_name(SHARED_SECRET_NAME)],
        "encrypted_ports": [PREVIEW_PORT],
        "env": env,
    }

    with modal.enable_output():
        sandbox = modal.Sandbox.create(
            *entrypoint_args,
            **sandbox_kwargs,
        )

    preview_url = ""
    try:
        tunnels = sandbox.tunnels()
        tunnel_obj = None
        if hasattr(tunnels, "get"):
            tunnel_obj = tunnels.get(PREVIEW_PORT)
        elif PREVIEW_PORT in tunnels:
            tunnel_obj = tunnels[PREVIEW_PORT]
        if tunnel_obj is not None and hasattr(tunnel_obj, "url"):
            preview_url = str(tunnel_obj.url)
    except Exception:
        pass

    return sandbox, preview_url


def spawn_preview_sandbox(config: PreviewSpawnConfig) -> tuple[modal.Sandbox, str]:
    """Convenience alias for create_preview_sandbox."""
    import factory.spawner

    return factory.spawner.create_preview_sandbox(config)

