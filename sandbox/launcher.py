"""Consolidated deep module for Modal sandbox provisioning.

Provides SandboxLauncher and RunningSandbox behind a clean execution seam,
encapsulating container image resolution, credential mounting, environment
compilation, tunnel negotiation, lifecycle registration, and SSH configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import secrets
import subprocess
from typing import Any, Callable
import uuid

import modal

from sandbox.config import (
    DEFAULT_METRO_PORT,
    DEFAULT_OPENCODE_PORT,
    DEFAULT_ORG,
    DEFAULT_T3_PORT,
    DEFAULT_WEB_PORT,
    IDLE_TIMEOUT_SECS,
    TIMEOUT_SECS,
)
from sandbox.core import (
    LaunchRequest,
    LaunchResponse,
    validate_launch_request,
)
from sandbox.formatting import append_ssh_config
from sandbox.t3 import setup_t3 as _setup_t3
from shared.image import (
    DEFAULT_T3_USAGE_VOLUME,
    REMOTE_STARTUP_SCRIPT,
    T3_STORAGE_MOUNT_PATH,
    browser_enabled,
    build_sandbox_image,
    get_gradle_volumes,
    get_t3_usage_volumes,
    load_ssh_pub_key,
)


@dataclass
class RunningSandbox:
    """Encapsulated running Modal sandbox instance and its connection metadata."""

    sandbox: modal.Sandbox
    response: LaunchResponse

    @property
    def sandbox_id(self) -> str:
        return self.response.sandbox_id

    @property
    def app_name(self) -> str:
        return self.response.app_name

    @property
    def sandbox_name(self) -> str:
        return self.response.sandbox_name

    @property
    def ssh_info(self) -> tuple[str, int] | None:
        return self.response.ssh_info

    @property
    def ssh_command(self) -> str | None:
        return self.response.ssh_command

    @property
    def opencode_url(self) -> str | None:
        return self.response.opencode_url

    @property
    def metro_url(self) -> str | None:
        return self.response.metro_url

    @property
    def t3_url(self) -> str | None:
        return self.response.t3_url

    @property
    def t3_pair_url(self) -> str | None:
        return self.response.t3_pair_url

    def to_response(self) -> LaunchResponse:
        """Returns the serializable Pydantic LaunchResponse."""
        return self.response

    def poll(self) -> int | None:
        """Polls the underlying sandbox status."""
        return self.sandbox.poll()

    def terminate(self) -> None:
        """Terminates the underlying sandbox."""
        self.sandbox.terminate()

    def exec(self, *cmd: str, **kwargs: Any) -> Any:
        """Executes a command inside the underlying sandbox."""
        return self.sandbox.exec(*cmd, **kwargs)

    def tunnels(self) -> dict[int, Any]:
        """Returns active network tunnels for the sandbox."""
        return self.sandbox.tunnels()

    def __iter__(self):
        """Allows unpacking as (sandbox, response) for backward compatibility."""
        return iter((self.sandbox, self.response))


def resolve_host_git_identity() -> dict[str, str]:
    """Dynamically resolves host Git identity from environment or git configuration."""
    git_env: dict[str, str] = {}
    name = os.environ.get("GIT_AUTHOR_NAME") or os.environ.get("GIT_COMMITTER_NAME")
    email = os.environ.get("GIT_AUTHOR_EMAIL") or os.environ.get("GIT_COMMITTER_EMAIL")
    if not name:
        try:
            res = subprocess.run(
                ["git", "config", "user.name"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                name = res.stdout.strip()
        except Exception:
            pass
    if not email:
        try:
            res = subprocess.run(
                ["git", "config", "user.email"],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0 and res.stdout.strip():
                email = res.stdout.strip()
        except Exception:
            pass

    if name:
        git_env["GIT_AUTHOR_NAME"] = name
        git_env["GIT_COMMITTER_NAME"] = name
    if email:
        git_env["GIT_AUTHOR_EMAIL"] = email
        git_env["GIT_COMMITTER_EMAIL"] = email
    return git_env


class SandboxLauncher:
    """Deep module for provisioning and configuring Modal sandboxes."""

    def __init__(
        self,
        client: modal.Client | None = None,
        build_image_fn: Callable[..., modal.Image] | None = None,
        load_pubkey_fn: Callable[[], str] | None = None,
        append_ssh_fn: Callable[..., bool] | None = None,
        resolve_git_identity_fn: Callable[[], dict[str, str]] | None = None,
        log_cb: Callable[[str], None] | None = None,
        repo_root: Path | None = None,
    ) -> None:
        self.client = client
        self.build_image_fn = build_image_fn or build_sandbox_image
        self.load_pubkey_fn = load_pubkey_fn or load_ssh_pub_key
        self.append_ssh_fn = append_ssh_fn or append_ssh_config
        self.resolve_git_identity_fn = resolve_git_identity_fn or resolve_host_git_identity
        self.log_cb = log_cb
        self.repo_root = repo_root

    def _emit_log(self, msg: str) -> None:
        if self.log_cb:
            try:
                self.log_cb(msg)
            except Exception:
                pass
        print(msg)

    def _resolve_repo_root(self) -> Path:
        if self.repo_root is not None:
            return self.repo_root
        if Path("/root/.env").is_file():
            return Path("/root")
        return Path(__file__).resolve().parent.parent

    def launch(
        self,
        req: LaunchRequest,
        register_ssh_config: bool = False,
    ) -> RunningSandbox:
        """Provisions a Modal sandbox and executes the post-launch setup pipeline."""
        self._emit_log("▶ Validating launch request...")
        validate_launch_request(req)

        repo_root = self._resolve_repo_root()
        clean_repo = req.repo.strip().rstrip("/") if req.repo else None
        target_repo, org_name, bare_repo = None, None, None

        has_gh_token = bool(os.environ.get("GH_TOKEN"))
        dotenv_file = repo_root / ".env"
        if dotenv_file.is_file():
            try:
                for line in dotenv_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not has_gh_token and line.startswith("GH_TOKEN="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val: has_gh_token = True; os.environ["GH_TOKEN"] = val
                    if not os.environ.get("GH_ORG_NAME") and line.startswith("GH_ORG_NAME="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val: os.environ["GH_ORG_NAME"] = val
                    if not os.environ.get("MODAL_TOKENS") and line.startswith("MODAL_TOKENS="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val: os.environ["MODAL_TOKENS"] = val
            except Exception:
                pass

        if req.modal:
            from sandbox.profiles import parse_modal_tokens_env
            if not parse_modal_tokens_env():
                raise ValueError("Modal development tooling (--modal) requires valid MODAL_TOKENS in environment or .env.")

        if clean_repo:
            if not has_gh_token:
                raise FileNotFoundError(
                    f"GitHub credentials (GH_TOKEN) not found in environment or {repo_root / '.env'}."
                )
            if "/" in clean_repo:
                org_name, raw_repo = clean_repo.split("/", 1)
            else:
                default_org = os.environ.get("GH_ORG_NAME") or DEFAULT_ORG
                if not default_org:
                    raise ValueError(
                        f"Target repository '{clean_repo}' has no owner prefix and GH_ORG_NAME is not set. "
                        f"Specify owner/repo (e.g. owner/{clean_repo}) or set GH_ORG_NAME."
                    )
                org_name, raw_repo = default_org, clean_repo

            bare_repo = (
                raw_repo
                if (not req.testing or raw_repo.startswith("test-"))
                else f"test-{raw_repo}"
            )
            target_repo = f"{org_name}/{bare_repo}"

        pubkey_content = self.load_pubkey_fn()
        random_id = uuid.uuid4().hex[:8]
        app_name = req.name if req.name else (bare_repo if bare_repo else "sandbox")
        sandbox_name = f"{app_name}-{random_id}"
        self._emit_log(f"🔑 Resolving App '{app_name}' and sandbox instance '{sandbox_name}'...")
        target_client = self.client
        if target_client is None and req.profile:
            from sandbox.profiles import get_client_for_profile
            target_client = get_client_for_profile(req.profile)

        app = (
            modal.App.lookup(app_name, client=target_client, create_if_missing=True)
            if target_client
            else modal.App.lookup(app_name, create_if_missing=True)
        )

        browser_active = browser_enabled(browser=req.browser, opencode=req.opencode, agy=req.agy)

        if req.from_snapshot:
            self._emit_log(f"🏗️ Loading container image from snapshot {req.from_snapshot}...")
            image = modal.Image.from_id(req.from_snapshot)
        else:
            self._emit_log("🏗️ Resolving container base image and tooling layers...")
            image = self.build_image_fn(
                opencode=req.opencode, agy=req.agy, browser=browser_active,
                modal_tooling=req.modal, react_native=req.react_native, t3=req.t3,
                herdr=req.herdr, pi=req.pi,
            )

        cloudflare_active = not req.no_cloudflare
        encrypted_ports: list[int] = []
        sandbox_secrets: list[modal.Secret] = []
        if dotenv_file.is_file():
            sandbox_secrets.append(modal.Secret.from_dotenv(dotenv_file))
        else:
            secret_keys = [
                "GH_TOKEN", "GH_ORG_NAME", "CLOUDFLARE_TUNNEL_TOKEN", "SSH_AUTHORIZED_KEY",
                "OPENCODE_GO_API_KEY", "ANTIGRAVITY_CLIENT_ID", "ANTIGRAVITY_CLIENT_SECRET",
                "ANTIGRAVITY_PROJECT_ID", "ANTIGRAVITY_TOKENS", "AGE_PRIVATE_KEY", "MODAL_TOKENS",
                "WEB_UI_USERNAME", "WEB_UI_PASSWORD", "MODAL_SANDBOX_AUTH_TOKEN",
            ]
            env_dict = {k: os.environ[k] for k in secret_keys if k in os.environ and os.environ[k]}
            if env_dict:
                sandbox_secrets.append(modal.Secret.from_dict(env_dict))
        env: dict[str, str | None] = {
            "SSH_AUTHORIZED_KEY": pubkey_content, "PORT": str(DEFAULT_WEB_PORT),
            "HOSTNAME": "0.0.0.0", "APP_NAME": sandbox_name,
            "MODAL_APP_NAME": app_name, "SANDBOX_NAME": sandbox_name,
        }
        env.update(self.resolve_git_identity_fn())

        if req.from_snapshot: env["RESUME_SNAPSHOT"] = "1"
        if clean_repo is None: env["NO_REPO"] = "1"
        if target_repo: env["GH_REPO"] = target_repo
        if org_name: env["GH_ORG"] = org_name
        if req.full_clone: env["FULL_CLONE"] = "1"
        if not cloudflare_active: env["ENABLE_CLOUDFLARE"] = "0"
        if req.profile: env["MODAL_PROFILE"] = req.profile
        elif os.environ.get("MODAL_PROFILE"): env["MODAL_PROFILE"] = os.environ["MODAL_PROFILE"]

        memory_gb: int | None = None
        if req.vm:
            memory_gb = req.memory if req.memory is not None else None
            env["SWAP_GB"] = str(memory_gb * 2 if memory_gb else 2)
            env["ENABLE_DOCKER"] = "1"

        opencode_password = None
        if req.opencode:
            encrypted_ports.append(req.opencode_port)
            opencode_password = secrets.token_urlsafe(16)
            sandbox_secrets.append(modal.Secret.from_dict({"OPENCODE_SERVER_PASSWORD": opencode_password}))
            env["ENABLE_OPENCODE"] = "1"
            env["OPENCODE_PORT"] = str(req.opencode_port)

        t3_persist_enabled = req.t3 and not req.no_t3_persist
        t3_ssh_alias = req.t3_ssh_host or sandbox_name
        if req.t3:
            encrypted_ports.append(req.t3_port)
            env["ENABLE_T3"] = "1"
            env["T3_PORT"] = str(req.t3_port)
            env["FLAGS_enforce_kernel_ipv6_support"] = "false"
            env["T3_SSH_HOST"] = t3_ssh_alias
            if t3_persist_enabled:
                env["ENABLE_T3_PERSISTENCE"] = "1"
                env["T3_USAGE_VOLUME"] = req.t3_usage_volume
                env["ANTIGRAVITY_DATA_DIR"] = f"{T3_STORAGE_MOUNT_PATH}/conversations"

        for flag, key in [
            (req.agy, "ENABLE_ANTIGRAVITY"), (req.modal, "ENABLE_MODAL"),
            (req.sops, "ENABLE_SOPS"), (req.herdr, "ENABLE_HERDR"),
            (req.pi, "ENABLE_PI"), (browser_active, "ENABLE_BROWSER"),
        ]:
            if flag: env[key] = "1"

        if req.react_native:
            encrypted_ports.append(req.metro_port)
            env["ENABLE_REACT_NATIVE"] = "1"
            env["METRO_PORT"] = str(req.metro_port)

        volumes: dict[str, modal.Volume] = {}
        if req.react_native:
            volumes.update(get_gradle_volumes())
        if t3_persist_enabled:
            volumes.update(get_t3_usage_volumes(name=req.t3_usage_volume))

        feature_flags = [
            (not req.no_cloudflare, "Cloudflare Tunnel"), (req.full_clone, "Full Git Clone"),
            (req.react_native, "React Native"), (req.agy, "Antigravity"),
            (req.opencode, "OpenCode"), (req.t3, "T3 Code"),
            (t3_persist_enabled, "T3 Usage Persistence"), (req.modal, "Modal"),
            (req.sops, "SOPS"), (req.herdr, "Herdr"),
            (req.pi, "Pi"), (browser_active, "Browser"),
        ]
        features = [label for active, label in feature_flags if active]
        runtime_desc = "VM Sandbox" if req.vm else "Sandbox"
        self._emit_log(f"📋 Configuration: {runtime_desc} | Features: {', '.join(features)}")

        sandbox_kwargs: dict[str, Any] = {
            "timeout": TIMEOUT_SECS, "idle_timeout": IDLE_TIMEOUT_SECS, "image": image,
            "app": app, "name": sandbox_name, "tags": {"instance_name": sandbox_name, "app_name": app_name},
            "volumes": volumes, "unencrypted_ports": [22], "encrypted_ports": encrypted_ports,
            "cpu": (0.125, 4.0), "env": env, "runtime": "vm" if req.vm else "gvisor",
            "memory": (128, 16384),
        }
        if target_client is not None:
            sandbox_kwargs["client"] = target_client

        self._emit_log("🚀 Instantiating Modal Sandbox container...")
        with modal.enable_output():
            sandbox = modal.Sandbox.create(
                "bash", REMOTE_STARTUP_SCRIPT, req.github_branch,
                secrets=sandbox_secrets, **sandbox_kwargs,
            )

        self._emit_log(f"📦 Modal Sandbox container created: {sandbox.object_id}")
        poll_val = sandbox.poll()
        if isinstance(poll_val, int) and poll_val != 0:
            err = ""
            try:
                err = (sandbox.stderr.read() or sandbox.stdout.read() or "").strip()
            except Exception:
                pass
            msg = f"Container terminated with exit code {poll_val}: {err}"
            self._emit_log(f"❌ {msg}")
            raise RuntimeError(msg)

        self._emit_log("🌐 Resolving network tunnels and connection endpoints...")
        ssh_info, opencode_url, metro_url, t3_url = None, None, None, None
        try:
            tunnels = sandbox.tunnels()
            if 22 in tunnels: ssh_info = tunnels[22].tcp_socket
            if req.opencode and req.opencode_port in tunnels: opencode_url = tunnels[req.opencode_port].url
            if req.react_native and req.metro_port in tunnels: metro_url = tunnels[req.metro_port].url
            if req.t3 and req.t3_port in tunnels: t3_url = tunnels[req.t3_port].url
        except Exception as exc:
            self._emit_log(f"⚠️ Could not obtain tunnel metadata: {exc}")

        t3_pair_url, t3_qr_code = None, None
        if req.t3 and t3_url:
            self._emit_log("⚡ Initializing T3 Code server and pairing credentials...")
            t3_pair_url, t3_qr_code = _setup_t3(sandbox, t3_url, t3_ssh_alias)
            if t3_pair_url:
                self._emit_log(f"✓ T3 Code server ready: {t3_pair_url}")

        ssh_cmd = (
            f"ssh -i ~/.ssh/modal-sandbox -o StrictHostKeyChecking=no -p {ssh_info[1]} root@{ssh_info[0]}"
            if ssh_info else f"modal shell {sandbox.object_id}"
        )

        try:
            from sandbox.lifecycle import record_sandbox_connection_info
            record_sandbox_connection_info(
                sandbox.object_id, ssh_command=ssh_cmd,
                t3_pair_url=t3_pair_url, has_t3=bool(req.t3),
            )
        except Exception:
            pass

        if register_ssh_config and ssh_info and not getattr(req, "no_ssh_config", False):
            instance_name = t3_ssh_alias or sandbox_name or app_name
            try:
                self.append_ssh_fn(
                    instance_name=instance_name,
                    ssh_host=ssh_info[0],
                    ssh_port=ssh_info[1],
                )
            except Exception as exc:
                self._emit_log(f"⚠️ Could not update SSH config: {exc}")

        self._emit_log(f"📡 SSH connection ready: {ssh_cmd}")
        self._emit_log("✨ Sandbox launched successfully! All background services active.")

        response = LaunchResponse(
            sandbox_id=sandbox.object_id, app_name=app_name, sandbox_name=sandbox_name,
            ssh_info=ssh_info, ssh_command=ssh_cmd, opencode_url=opencode_url,
            opencode_port=req.opencode_port if req.opencode else None,
            opencode_password=opencode_password,
            metro_url=metro_url, metro_port=req.metro_port if req.react_native else None,
            t3_url=t3_url, t3_port=req.t3_port if req.t3 else None,
            t3_pair_url=t3_pair_url, t3_qr_code=t3_qr_code, t3_ssh_host=t3_ssh_alias,
            t3_persist=t3_persist_enabled,
            t3_usage_volume=req.t3_usage_volume if t3_persist_enabled else None,
            memory_gb=memory_gb, agy_enabled=req.agy,
            cloudflare_enabled=cloudflare_active, sops_enabled=req.sops, is_vm=req.vm,
        )
        return RunningSandbox(sandbox=sandbox, response=response)

    @classmethod
    def run(
        cls,
        req: LaunchRequest,
        repo_root: Path | None = None,
        build_image_fn: Callable | None = None,
        load_pubkey_fn: Callable | None = None,
        append_ssh_fn: Callable | None = None,
        resolve_git_identity_fn: Callable[[], dict[str, str]] | None = None,
        client: modal.Client | None = None,
        log_cb: Callable[[str], None] | None = None,
        register_ssh_config: bool = False,
    ) -> RunningSandbox:
        """Instantiates a SandboxLauncher and launches the requested sandbox."""
        launcher = cls(
            client=client, build_image_fn=build_image_fn, load_pubkey_fn=load_pubkey_fn,
            append_ssh_fn=append_ssh_fn, resolve_git_identity_fn=resolve_git_identity_fn,
            log_cb=log_cb, repo_root=repo_root,
        )
        return launcher.launch(req, register_ssh_config=register_ssh_config)


def launch_sandbox(
    req: LaunchRequest,
    repo_root: Path | None = None,
    build_image_fn: Callable | None = None,
    load_pubkey_fn: Callable | None = None,
    client: modal.Client | None = None,
    log_cb: Callable[[str], None] | None = None,
    register_ssh_config: bool = False,
    append_ssh_fn: Callable | None = None,
    resolve_git_identity_fn: Callable[[], dict[str, str]] | None = None,
) -> RunningSandbox:
    """Convenience functional seam delegating to SandboxLauncher."""
    return SandboxLauncher.run(
        req=req, repo_root=repo_root, build_image_fn=build_image_fn,
        load_pubkey_fn=load_pubkey_fn, append_ssh_fn=append_ssh_fn,
        resolve_git_identity_fn=resolve_git_identity_fn,
        client=client, log_cb=log_cb, register_ssh_config=register_ssh_config,
    )
