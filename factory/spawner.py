"""Modal Factory Sandbox Spawner and Provisioning Engine.

Provisions ephemeral Modal Sandboxes (Standard Sandboxes with burstable memory
by default, or VM Sandboxes when virtualization is requested) running the
assembly line pipeline with mounted factory harness and scoped credentials.
"""

from dataclasses import dataclass
from pathlib import Path
import sys
import threading
from typing import Any, TextIO
import uuid

import modal

from shared.image import (
    LOCAL_OPENCODE_SECRET,
    REMOTE_CLOUDFLARE_SECRET,
    REMOTE_FACTORY_ENTRYPOINT,
    REMOTE_OPENCODE_SECRET,
    REMOTE_ORG_SECRETS_DIR,
    REMOTE_REPO_SECRETS_DIR,
    SHARED_SECRET_NAME,
    base_image,
)

DEFAULT_TEST_ORG: str = "software-factory-09-test"

# Reused timeout constants matching sandbox/main.py
FACTORY_TIMEOUT_SECS: int = 16 * 60 * 60  # 16 hours
FACTORY_IDLE_TIMEOUT_SECS: int = 4 * 60 * 60  # 4 hours

# Resource specifications
FACTORY_STANDARD_MEMORY: tuple[int, int] = (128, 16384)  # 128 MiB request, 16 GiB burstable limit
FACTORY_VM_DEFAULT_MEMORY_GB: int = 1
FACTORY_CPU: tuple[float, float] = (0.125, 4.0)


# Dedicated preview constants per ADR 0037
PREVIEW_PORT: int = 3000
PREVIEW_IDLE_TIMEOUT_SECS: int = 1800  # 30 minutes
PREVIEW_ALLOWED_HOSTS: str = ".modal.host,3000.mahesh0.dev"


@dataclass
class PreviewSpawnConfig:
    """Configuration options for spawning a Modal Dedicated Preview Sandbox."""

    repo: str
    branch: str = "main"
    testing: bool = True
    timeout_secs: int = FACTORY_TIMEOUT_SECS
    idle_timeout_secs: int = PREVIEW_IDLE_TIMEOUT_SECS
    app_name: str | None = None
    repo_root: Path | None = None
    install_deps: bool = True


@dataclass
class FactorySpawnConfig:
    """Configuration options for spawning a Modal software factory sandbox."""

    project: str
    feature: str
    issue: str | None = None
    tracker: str | None = None
    vm: bool = False
    testing: bool = False
    model: str | None = None
    memory_gb: int | None = None
    timeout_secs: int = FACTORY_TIMEOUT_SECS
    idle_timeout_secs: int = FACTORY_IDLE_TIMEOUT_SECS
    app_name: str | None = None
    repo_root: Path | None = None
    install_deps: bool = True
    dev: bool = False


def resolve_repo_root(repo_root: Path | None = None) -> Path:
    """Resolves the software factory repository root directory."""
    if repo_root is not None:
        return repo_root.resolve()
    return Path(__file__).resolve().parent.parent


def normalize_project_name(project: str) -> tuple[str, bool]:
    """Normalizes project input, extracting bare or qualified project name and detecting testing mode.

    Handles 'secrets/<project-name>', 'secrets_org/<org>/<repo>', 'secrets_org/<org>',
    '<org>/<repo>', 'secrets_testing/<project-name>', or bare '<project-name>'.
    """
    clean = project.strip().rstrip("/")
    is_testing = False
    if clean.startswith("secrets_testing/"):
        clean = clean[len("secrets_testing/"):]
        is_testing = True
    elif clean.startswith("secrets_org/"):
        clean = clean[len("secrets_org/"):]
        is_testing = True
    elif clean.startswith("secrets/"):
        clean = clean[len("secrets/"):]
    elif clean.startswith(f"{DEFAULT_TEST_ORG}/") or clean == DEFAULT_TEST_ORG:
        is_testing = True
    return clean, is_testing


def resolve_target_repo(project: str, testing: bool = False) -> str | None:
    """Resolves the GitHub target repository string (e.g. 'software-factory-09-test/test3') if applicable."""
    clean_project, detected_testing = normalize_project_name(project)
    effective_testing = testing or detected_testing
    if effective_testing:
        if "/" in clean_project:
            return clean_project
        if clean_project == DEFAULT_TEST_ORG:
            return None
        return f"{DEFAULT_TEST_ORG}/{clean_project}"
    return None


def resolve_secrets_dir(
    project: str,
    testing: bool = False,
    repo_root: Path | None = None,
) -> Path:
    """Resolves and validates the target project or organization secret directory.

    Args:
        project: Project secret name (e.g. 'repo-horizon', 'test3',
                 'software-factory-09-test/test3', or 'secrets/repo-horizon').
        testing: Whether to resolve from canonical Test Organization under
                 'secrets_org/' per ADR 0031.
        repo_root: Software factory repository root directory.

    Returns:
        Path to the project or organization secrets directory.

    Raises:
        FileNotFoundError: If the directory, fetch.env, or token is not found.
    """
    root = resolve_repo_root(repo_root)
    clean_project, detected_testing = normalize_project_name(project)
    effective_testing = testing or detected_testing

    if effective_testing:
        if "/" in clean_project:
            org_name = clean_project.split("/", 1)[0]
        else:
            if (root / "secrets_org" / clean_project).is_dir():
                org_name = clean_project
            else:
                org_name = DEFAULT_TEST_ORG

        org_dir = root / "secrets_org" / org_name
        if not org_dir.is_dir():
            raise FileNotFoundError(
                f"Target organization secrets directory not found: {org_dir} "
                f"(expected under secrets_org/{org_name})."
            )

        token_file = org_dir / "token"
        if not token_file.is_file():
            raise FileNotFoundError(
                f"Organization token secret not found: {token_file} "
                f"(expected secrets_org/{org_name}/token)."
            )

        return org_dir

    project_dir = root / "secrets" / clean_project
    if not project_dir.is_dir():
        raise FileNotFoundError(
            f"Target project secrets directory not found: {project_dir} "
            f"(expected under secrets/{clean_project})."
        )

    fetch_file = project_dir / "fetch.env"
    if not fetch_file.is_file():
        raise FileNotFoundError(
            f"Repository fetch secret not found: {fetch_file} "
            f"(expected secrets/{clean_project}/fetch.env)."
        )

    return project_dir


def get_factory_app_name(project: str, testing: bool = False) -> str:
    """Generates an ephemeral Modal app name conforming to ADR 0031.

    Test sandboxes are prefixed with 'test-' per ADR 0031.
    """
    clean_project, detected_testing = normalize_project_name(project)
    effective_testing = testing or detected_testing
    bare_name = clean_project.split("/")[-1]
    random_id = uuid.uuid4().hex[:8]
    prefix = "test-" if effective_testing else ""
    return f"{prefix}{bare_name}-{random_id}"


def build_factory_image(
    project_secrets_dir: Path,
    factory_dir: Path,
    repo_root: Path | None = None,
    install_deps: bool = True,
) -> modal.Image:
    """Builds the Modal Image for the software factory sandbox.

    Mounts:
      - Project secrets into /root/secrets/repo/
      - OpenCode secret into /root/secrets/opencode.env
      - Factory harness (sandbox/factory/) into /root/factory/
      - Dedicated container entrypoint into /root/factory_entrypoint.sh

    Args:
        project_secrets_dir: Local path to staged project secrets directory.
        factory_dir: Local path to sandbox/factory TypeScript harness.
        repo_root: Repository root path.
        install_deps: Whether to run pnpm install inside the image layer.

    Returns:
        Configured modal.Image instance.
    """
    root = resolve_repo_root(repo_root)
    image = base_image

    # Stage OpenCode secret for in-container decryption
    opencode_secret = root / "secrets" / "opencode.env"
    if opencode_secret.is_file():
        image = image.add_local_file(
            opencode_secret, REMOTE_OPENCODE_SECRET, copy=True
        )

    # Stage dedicated factory container entrypoint
    entrypoint_script = root / "shared" / "factory_entrypoint.sh"
    if entrypoint_script.is_file():
        image = image.add_local_file(
            entrypoint_script, REMOTE_FACTORY_ENTRYPOINT, copy=True
        )

    # Stage Cloudflare Tunnel secret for dev preview keep-alive
    cloudflare_secret = root / "secrets" / "cloudflare.env"
    if cloudflare_secret.is_file():
        image = image.add_local_file(
            cloudflare_secret, REMOTE_CLOUDFLARE_SECRET, copy=True
        )

    # Stage target project or organization secrets
    if (project_secrets_dir / "token").is_file():
        image = image.add_local_dir(
            project_secrets_dir, REMOTE_ORG_SECRETS_DIR, copy=True
        )
    else:
        image = image.add_local_dir(
            project_secrets_dir, REMOTE_REPO_SECRETS_DIR, copy=True
        )

    # Mount local factory harness into /root/factory
    image = image.add_local_dir(
        factory_dir, "/root/factory", copy=True, ignore=["node_modules"]
    )

    # Optionally pre-install dependencies into the image layer
    if install_deps:
        image = image.run_commands(
            "cd /root/factory && pnpm install --force --shamefully-hoist"
        )

    return image


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
    return create_factory_sandbox(config)


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
    return create_preview_sandbox(config)


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
    sandbox = create_factory_sandbox(config)
    return stream_sandbox_logs(sandbox, stdout=stdout, stderr=stderr)
