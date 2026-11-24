"""Consolidated deep module for Modal sandbox provisioning.

Provides SandboxLauncher and RunningSandbox behind a clean execution seam,
encapsulating container image resolution, credential mounting, environment
compilation, tunnel negotiation, lifecycle registration, and SSH configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import json
import secrets
import subprocess
from typing import Any, Callable
import uuid

from datetime import datetime, timezone
import base64
import modal

from sandbox.env_store import (
    VaultBundle, fetch_vault_env, fetch_vault_env_bundle, fetch_vault_env_raw,
    fetch_vault_git_identity, parse_env_text, resolve_sandbox_bundle, serialize_env_dict,
)
from sandbox.provenance import resolve_host_git_identity, resolve_host_software_factory_provenance
from sandbox.config import (
    DEFAULT_METRO_PORT, DEFAULT_ORG, DEFAULT_T3_PORT, DEFAULT_WEB_PORT,
    IDLE_TIMEOUT_SECS, TEST_BASELINE_REPO, TIMEOUT_SECS, resolve_factory_credentials, resolve_timezone,
)
from sandbox.codex_profiles import prepare_profile
from sandbox.core import LaunchRequest, LaunchResponse, validate_launch_request
from sandbox.formatting import append_ssh_config, generate_ssh_config_snippet
from sandbox.t3 import setup_t3 as _setup_t3
from shared.image import (
    DEFAULT_T3_USAGE_VOLUME, REMOTE_STARTUP_SCRIPT, T3_STORAGE_MOUNT_PATH,
    browser_enabled, build_sandbox_image, get_gradle_volumes,
    get_t3_usage_volumes, load_ssh_pub_key,
)


@dataclass
class RunningSandbox:
    """Encapsulated running Modal sandbox instance and its connection metadata."""

    sandbox: modal.Sandbox
    response: LaunchResponse

    @property
    def sandbox_id(self) -> str: return self.response.sandbox_id
    @property
    def app_name(self) -> str: return self.response.app_name
    @property
    def sandbox_name(self) -> str: return self.response.sandbox_name
    @property
    def ssh_info(self) -> tuple[str, int] | None: return self.response.ssh_info
    @property
    def ssh_command(self) -> str | None: return self.response.ssh_command
    @property
    def stdout(self) -> Any: return self.sandbox.stdout
    @property
    def stderr(self) -> Any: return self.sandbox.stderr
    @property
    def stdin(self) -> Any: return self.sandbox.stdin
    @property
    def returncode(self) -> int | None: return self.sandbox.returncode

    def to_response(self) -> LaunchResponse: return self.response
    def poll(self) -> int | None: return self.sandbox.poll()
    def wait(self, raise_on_error: bool = True) -> int: return self.sandbox.wait(raise_on_error=raise_on_error)
    def terminate(self) -> None: self.sandbox.terminate()
    def exec(self, *cmd: str, **kwargs: Any) -> Any: return self.sandbox.exec(*cmd, **kwargs)
    def tunnels(self) -> dict[int, Any]: return self.sandbox.tunnels()
    def __iter__(self): return iter((self.sandbox, self.response))
    def __getattr__(self, name: str) -> Any: return getattr(self.response, name)


class SandboxLauncher:
    """Deep module for provisioning and configuring Modal sandboxes."""

    def __init__(
        self,
        client: modal.Client | None = None,
        build_image_fn: Callable[..., modal.Image] | None = None,
        load_pubkey_fn: Callable[[], str] | None = None,
        append_ssh_fn: Callable[..., bool] | None = None,
        resolve_git_identity_fn: Callable[[], dict[str, str]] | None = None,
        resolve_provenance_fn: Callable[[Path | None], dict[str, str]] | None = None,
        fetch_vault_env_fn: Callable[..., dict[str, str] | None] | None = None,
        fetch_vault_env_raw_fn: Callable[..., str | None] | None = None,
        fetch_vault_env_bundle_fn: Callable[..., dict[str, Any] | None] | None = None,
        fetch_vault_git_identity_fn: Callable[..., dict[str, str] | None] | None = None,
        resolve_vault_bundle_fn: Callable[..., VaultBundle | None] | None = None,
        log_cb: Callable[[str], None] | None = None, repo_root: Path | None = None,
    ) -> None:
        self.client = client
        self.build_image_fn = build_image_fn or build_sandbox_image
        self.load_pubkey_fn = load_pubkey_fn or load_ssh_pub_key
        self.append_ssh_fn = append_ssh_fn or append_ssh_config
        self.resolve_git_identity_fn = resolve_git_identity_fn or resolve_host_git_identity
        self.resolve_provenance_fn = resolve_provenance_fn or resolve_host_software_factory_provenance
        self.fetch_vault_env_fn = fetch_vault_env_fn
        self.fetch_vault_env_raw_fn = fetch_vault_env_raw_fn
        self.fetch_vault_env_bundle_fn = fetch_vault_env_bundle_fn
        self.fetch_vault_git_identity_fn = fetch_vault_git_identity_fn
        self.resolve_vault_bundle_fn = resolve_vault_bundle_fn or (
            resolve_sandbox_bundle
            if (fetch_vault_env_fn is None and fetch_vault_env_raw_fn is None and fetch_vault_env_bundle_fn is None)
            else None
        )
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
        dotenv_file = repo_root / ".env"
        clean_repo = req.repo.strip().rstrip("/") if req.repo else None
        target_repo, org_name, bare_repo = None, None, None
        testing_baseline = False

        creds = resolve_factory_credentials(repo_root=repo_root, mutate_environ=True)
        has_gh_token = bool(creds.gh_token or os.environ.get("GH_TOKEN"))

        if req.modal:
            from sandbox.profiles import parse_modal_tokens_env
            if not parse_modal_tokens_env():
                raise ValueError("Modal development tooling (--modal) requires valid MODAL_TOKENS in environment or .env.")

        if clean_repo:
            if not has_gh_token:
                raise FileNotFoundError(
                    f"GitHub credentials (GH_TOKEN) not found in environment or {repo_root / '.env'}."
                )
            default_org = os.environ.get("GH_ORG_NAME") or DEFAULT_ORG
            if "/" in clean_repo:
                org_name, raw_repo = clean_repo.split("/", 1)
            else:
                if not default_org:
                    raise ValueError(
                        f"Target repository '{clean_repo}' has no owner prefix and GH_ORG_NAME is not set. "
                        f"Specify owner/repo (e.g. owner/{clean_repo}) or set GH_ORG_NAME."
                    )
                org_name, raw_repo = default_org, clean_repo

            testing_baseline = req.testing and (org_name.casefold(), raw_repo.casefold()) == (
                default_org.casefold(), TEST_BASELINE_REPO,
            )
            bare_repo = (
                raw_repo
                if (not req.testing or testing_baseline or raw_repo.startswith("test-"))
                else f"test-{raw_repo}"
            )
            target_repo = f"{org_name}/{bare_repo}"

        random_id = uuid.uuid4().hex[:8]
        default_app_name = f"test-{bare_repo}" if testing_baseline else bare_repo
        app_name = req.name or default_app_name or "sandbox"
        sandbox_name = f"{app_name}-{random_id}"
        self._emit_log(f"🔑 Resolving App '{app_name}' and sandbox instance '{sandbox_name}'...")

        pubkey_content = self.load_pubkey_fn()
        target_client = self.client
        if target_client is None and req.profile:
            from sandbox.profiles import get_client_for_profile
            target_client = get_client_for_profile(req.profile)

        app = (
            modal.App.lookup(app_name, client=target_client, create_if_missing=True)
            if target_client
            else modal.App.lookup(app_name, create_if_missing=True)
        )

        browser_active = browser_enabled(browser=req.browser, t3=req.t3)

        if req.from_snapshot:
            self._emit_log(f"🏗️ Loading container image from snapshot {req.from_snapshot}...")
            image = modal.Image.from_id(req.from_snapshot)
        else:
            self._emit_log("🏗️ Resolving container base image and tooling layers...")
            image = self.build_image_fn(
                browser=browser_active,
                modal_tooling=req.modal,
                react_native=req.react_native,
                t3=req.t3,
                xfce=req.xfce,
            )

        cloudflare_active = not req.no_cloudflare
        encrypted_ports: list[int] = []
        sandbox_secrets: list[modal.Secret] = []
        if "CODEX_STATUS_SECRET" in creds.extra_env:
            from dotenv import dotenv_values
            sandbox_secrets.append(modal.Secret.from_dict({
                k: v for k, v in dotenv_values(dotenv_file).items() if k != "CODEX_STATUS_SECRET" and v is not None
            }))
        elif dotenv_file.is_file():
            sandbox_secrets.append(modal.Secret.from_dotenv(dotenv_file))
        else:
            secret_keys = [
                "GH_TOKEN", "GH_ORG_NAME", "CLOUDFLARE_TUNNEL_TOKEN", "SSH_AUTHORIZED_KEY",
                "OPENCODE_GO_API_KEY", "ANTIGRAVITY_CLIENT_ID", "ANTIGRAVITY_CLIENT_SECRET",
                "ANTIGRAVITY_TOKENS", "AGE_PRIVATE_KEY", "MODAL_TOKENS",
                "WEB_UI_USERNAME", "WEB_UI_PASSWORD",
            ]
            env_dict = {k: os.environ[k] for k in secret_keys if k in os.environ and os.environ[k]}
            if env_dict:
                sandbox_secrets.append(modal.Secret.from_dict(env_dict))

        target_tz = resolve_timezone(repo_root)
        env: dict[str, str | None] = {
            "SSH_AUTHORIZED_KEY": pubkey_content, "PORT": str(DEFAULT_WEB_PORT),
            "HOSTNAME": "0.0.0.0", "APP_NAME": sandbox_name,
            "MODAL_APP_NAME": app_name, "SANDBOX_NAME": sandbox_name,
            "TZ": target_tz, "DEFAULT_TIMEZONE": target_tz,
        }
        env.update(self.resolve_git_identity_fn())
        provenance = self.resolve_provenance_fn(repo_root)
        env.update(provenance)

        if bare_repo:
            try:
                vault_bundle: VaultBundle | None = None
                if self.resolve_vault_bundle_fn:
                    vault_bundle = self.resolve_vault_bundle_fn(bare_repo, org_name=org_name)
                elif self.fetch_vault_env_bundle_fn:
                    b = self.fetch_vault_env_bundle_fn(bare_repo, org_name=org_name)
                    if b:
                        all_v = {k: v for c in b.get("files", {}).values() if isinstance(c, str) for k, v in parse_env_text(c).items()}
                        raw = b.get("files", {}).get("default.env") or (next(iter(b["files"].values())) if b.get("files") else None)
                        git_id = self.fetch_vault_git_identity_fn(bare_repo, org_name=org_name) if self.fetch_vault_git_identity_fn else {}
                        vault_bundle = VaultBundle(
                            env_dict=all_v, encoded_bundle=base64.b64encode(json.dumps(b).encode("utf-8")).decode("ascii"),
                            dotenv_b64=base64.b64encode(raw.encode("utf-8")).decode("ascii") if raw else None,
                            git_author_name=(git_id or {}).get("GIT_AUTHOR_NAME"),
                            git_author_email=(git_id or {}).get("GIT_AUTHOR_EMAIL"), tz=all_v.get("TZ"),
                        )
                if vault_bundle is None and (self.fetch_vault_env_raw_fn or self.fetch_vault_env_fn or self.fetch_vault_git_identity_fn):
                    raw_v, v_dict = None, None
                    if self.fetch_vault_env_raw_fn:
                        raw_v = self.fetch_vault_env_raw_fn(bare_repo, org_name=org_name)
                        if raw_v is not None: v_dict = parse_env_text(raw_v)
                    if v_dict is None and self.fetch_vault_env_fn:
                        v_dict = self.fetch_vault_env_fn(bare_repo, org_name=org_name)
                        if v_dict is not None: raw_v = serialize_env_dict(v_dict)
                    git_id = self.fetch_vault_git_identity_fn(bare_repo, org_name=org_name) if self.fetch_vault_git_identity_fn else {}
                    vault_bundle = VaultBundle(
                        env_dict=v_dict or {},
                        dotenv_b64=base64.b64encode(raw_v.encode("utf-8")).decode("ascii") if raw_v else None,
                        git_author_name=(git_id or {}).get("GIT_AUTHOR_NAME"),
                        git_author_email=(git_id or {}).get("GIT_AUTHOR_EMAIL"), tz=(v_dict or {}).get("TZ"),
                    )
                if vault_bundle:
                    if vault_bundle.encoded_bundle: env["VAULT_ENV_BUNDLE_B64"] = vault_bundle.encoded_bundle
                    if vault_bundle.dotenv_b64: env["VAULT_DOTENV_B64"] = vault_bundle.dotenv_b64
                    if vault_bundle.git_author_name: env["TARGET_GIT_AUTHOR_NAME"] = vault_bundle.git_author_name
                    if vault_bundle.git_author_email:
                        env["TARGET_GIT_AUTHOR_EMAIL"] = vault_bundle.git_author_email
                        self._emit_log(f"👤 Resolved repo-specific Git identity from env-store for {bare_repo}...")
                    if vault_bundle.tz: env["TZ"] = vault_bundle.tz
                    if vault_bundle.env_dict:
                        sandbox_secrets.append(modal.Secret.from_dict(vault_bundle.env_dict))
                        self._emit_log(f"🔐 Injected {len(vault_bundle.env_dict)} secrets from env-store into {bare_repo}...")
                    else:
                        self._emit_log(f"ℹ️ No secrets found for {bare_repo} in env-store.")
            except Exception as e:
                self._emit_log(f"⚠️ env-store resolution skipped: {e}")

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

        for flag, key in [(req.modal, "ENABLE_MODAL"), (req.sops, "ENABLE_SOPS"), (browser_active, "ENABLE_BROWSER")]:
            if flag: env[key] = "1"

        if req.xfce:
            env["ENABLE_XFCE"] = "1"
            env["XFCE_PORT"] = str(req.xfce_port)
            if req.xfce_password:
                env["XFCE_PASSWORD"] = req.xfce_password
            if req.xfce_port != DEFAULT_WEB_PORT:
                encrypted_ports.append(req.xfce_port)

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
            (req.react_native, "React Native"), (req.t3, "T3 Code"),
            (t3_persist_enabled, "T3 Usage Persistence"), (req.modal, "Modal"),
            (req.sops, "SOPS"), (browser_active, "Browser"),
            (req.xfce, "XFCE Desktop"),
        ]
        features = [label for active, label in feature_flags if active]
        runtime_desc = "VM Sandbox" if req.vm else "Sandbox"
        self._emit_log(f"📋 Configuration: {runtime_desc} | Features: {', '.join(features)}")

        created_at_iso = datetime.now(timezone.utc).isoformat()
        tags: dict[str, str] = {
            "instance_name": sandbox_name, "app_name": app_name,
            "software_factory_commit": provenance.get("SOFTWARE_FACTORY_COMMIT_SHORT", "unknown"),
            "software_factory_dirty": provenance.get("SOFTWARE_FACTORY_DIRTY", "0"),
            "created_at": created_at_iso, "timeout_secs": str(TIMEOUT_SECS),
            "timezone": str(env.get("TZ") or target_tz),
        }

        sandbox_kwargs: dict[str, Any] = {
            "timeout": TIMEOUT_SECS, "idle_timeout": IDLE_TIMEOUT_SECS, "image": image,
            "app": app, "name": sandbox_name, "tags": tags,
            "volumes": volumes, "unencrypted_ports": [22], "encrypted_ports": encrypted_ports,
            "cpu": (0.125, 4.0), "env": env, "runtime": "vm" if req.vm else "gvisor",
            "memory": (128, 16384),
        }
        if target_client is not None:
            sandbox_kwargs["client"] = target_client

        codex = None
        if req.t3 and not req.from_snapshot:
            codex = prepare_profile({**os.environ, **creds.extra_env}, req, target_client, env, volumes, tags)
            self._emit_log(f"Codex profile: {codex.label if codex else 'none (manual sign-in)'}")

        self._emit_log("🚀 Instantiating Modal Sandbox container...")
        with modal.enable_output():
            sandbox = modal.Sandbox.create(
                "bash", REMOTE_STARTUP_SCRIPT, req.github_branch,
                secrets=sandbox_secrets, **sandbox_kwargs,
            )

        self._emit_log(f"📦 Modal Sandbox container created: {sandbox.object_id}")
        if codex:
            try:
                codex.record(sandbox_name, app_name, sandbox.object_id)
            except (modal.exception.Error, OSError):
                self._emit_log("Could not save Codex owner ID. The pending reservation can be reconciled by name.")
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
        ssh_info, metro_url, t3_url, xfce_url = None, None, None, None
        try:
            tunnels = sandbox.tunnels()
            if 22 in tunnels: ssh_info = tunnels[22].tcp_socket
            if req.react_native and req.metro_port in tunnels: metro_url = tunnels[req.metro_port].url
            if req.t3 and req.t3_port in tunnels: t3_url = tunnels[req.t3_port].url
            if req.xfce:
                if req.xfce_port != DEFAULT_WEB_PORT and req.xfce_port in tunnels:
                    xfce_url = tunnels[req.xfce_port].url
                elif cloudflare_active:
                    tunnel_domain = os.getenv("MODAL_SANDBOX_TUNNEL_DOMAIN") or os.getenv("CLOUDFLARE_TUNNEL_DOMAIN", "")
                    if tunnel_domain:
                        domain_url = tunnel_domain if tunnel_domain.startswith(("http://", "https://")) else f"https://{tunnel_domain}"
                        xfce_url = f"{domain_url}/vnc.html?autoconnect=true&resize=remote"
                    else:
                        xfce_url = f"http://localhost:{req.xfce_port}/vnc.html?autoconnect=true&resize=remote"
                else:
                    xfce_url = f"http://localhost:{req.xfce_port}/vnc.html?autoconnect=true&resize=remote"
        except Exception as exc:
            self._emit_log(f"⚠️ Failed resolving tunnel URLs: {exc}")

        t3_pair_url, t3_qr_code = None, None
        if req.t3 and t3_url:
            self._emit_log("⚡ Initializing T3 Code server and pairing credentials...")
            t3_pair_url, t3_qr_code = _setup_t3(sandbox, t3_url, t3_ssh_alias)
            if t3_pair_url:
                self._emit_log(f"✓ T3 Code server ready: {t3_pair_url}")

        ssh_cmd, ssh_config_snippet = None, None
        instance_name = sandbox_name
        if ssh_info:
            ssh_cmd = f"ssh -i ~/.ssh/modal_sandbox -o StrictHostKeyChecking=no -p {ssh_info[1]} root@{ssh_info[0]}"
            ssh_config_snippet = generate_ssh_config_snippet(
                instance_name=instance_name, ssh_host=ssh_info[0], ssh_port=ssh_info[1],
            )

        try:
            from sandbox.lifecycle import record_sandbox_connection_info
            record_sandbox_connection_info(
                sandbox.object_id, ssh_command=ssh_cmd, ssh_config=ssh_config_snippet,
                t3_pair_url=t3_pair_url, has_t3=bool(req.t3),
                created_at=created_at_iso, timeout_secs=TIMEOUT_SECS,
            )
        except Exception:
            pass

        if register_ssh_config and ssh_info and not getattr(req, "no_ssh_config", False):
            try:
                self.append_ssh_fn(
                    instance_name=instance_name, ssh_host=ssh_info[0], ssh_port=ssh_info[1],
                )
            except Exception as exc:
                self._emit_log(f"⚠️ Could not update SSH config: {exc}")

        self._emit_log(f"📡 SSH connection ready: {ssh_cmd}")
        self._emit_log("✨ Sandbox launched successfully! All background services active.")

        response = LaunchResponse(
            sandbox_id=sandbox.object_id, app_name=app_name, sandbox_name=sandbox_name,
            ssh_info=ssh_info, ssh_command=ssh_cmd, ssh_config=ssh_config_snippet,
            metro_url=metro_url, metro_port=req.metro_port if req.react_native else None,
            t3_url=t3_url, t3_port=req.t3_port if req.t3 else None,
            t3_pair_url=t3_pair_url, t3_qr_code=t3_qr_code, t3_ssh_host=t3_ssh_alias,
            codex_profile=codex.label if codex else None,
            t3_persist=t3_persist_enabled,
            t3_usage_volume=req.t3_usage_volume if t3_persist_enabled else None,
            xfce_url=xfce_url, xfce_port=req.xfce_port if req.xfce else None,
            xfce_password=req.xfce_password if req.xfce else None,
            memory_gb=memory_gb,
            cloudflare_enabled=cloudflare_active, sops_enabled=req.sops, is_vm=req.vm,
        )
        return RunningSandbox(sandbox=sandbox, response=response)

    @classmethod
    def run(
        cls,
        req: LaunchRequest,
        repo_root: Path | None = None,
        register_ssh_config: bool = False,
        **kwargs: Any,
    ) -> RunningSandbox:
        """Instantiates a SandboxLauncher and launches the requested sandbox."""
        launcher = cls(repo_root=repo_root, **kwargs)
        return launcher.launch(req, register_ssh_config=register_ssh_config)


def launch_sandbox(
    req: LaunchRequest,
    repo_root: Path | None = None,
    register_ssh_config: bool = False,
    **kwargs: Any,
) -> RunningSandbox:
    """Convenience functional seam delegating to SandboxLauncher."""
    return SandboxLauncher.run(
        req=req,
        repo_root=repo_root,
        register_ssh_config=register_ssh_config,
        **kwargs,
    )
