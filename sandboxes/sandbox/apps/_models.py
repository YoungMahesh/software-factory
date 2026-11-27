"""Domain schemas and launch step helpers for Factory Apps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ._prompts import (  # noqa: F401
    MAX_SLUG_LENGTH,
    MAX_TITLE_LENGTH,
    AppTemplateKind,
    build_direct_chat_url,
    build_initial_thread_prompt,
    derive_app_slug,
    derive_app_title,
    derive_worktree_branch,
    prime_compatibility_key,
    prime_compatibility_key_for_app,
    prime_sandbox_app_name,
)
from ._workspace import shared_repo_base_dir
from sandbox.config import DEFAULT_METRO_PORT, DEFAULT_T3_PORT, DEFAULT_XFCE_PORT
from shared.image import DEFAULT_T3_USAGE_VOLUME

DEFAULT_BUILDER_PROVIDER = "antigravity"
DEFAULT_BUILDER_MODEL = "gemini-4-hydrogen"
DEFAULT_APP_BASE_PORT = 3001

HANDOFF_TOKEN_TTL_SECONDS = 300
MAX_LAUNCH_LOG_LINES = 80

LaunchStatus = Literal[
    "queued",
    "launching_sandbox",
    "scaffolding_workspace",
    "waiting_t3",
    "starting_thread",
    "ready",
    "failed",
]

PrimeStatus = Literal["provisioning", "ready", "failed", "stopped"]
RESUMABLE_STEPS: tuple[LaunchStatus, ...] = ("scaffolding_workspace", "waiting_t3", "starting_thread")


def utc_now_iso(*, offset_seconds: int = 0) -> str:
    """Returns the current UTC timestamp (optionally shifted) in ISO 8601 format."""
    now = datetime.now(timezone.utc)
    if offset_seconds:
        now = now + timedelta(seconds=offset_seconds)
    return now.isoformat()


def is_iso_expired(timestamp: str | None) -> bool:
    """Returns True when an ISO 8601 timestamp parses and lies at or before now."""
    if not timestamp:
        return False
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed <= datetime.now(timezone.utc)


class ModelOption(BaseModel):
    """Selectable option value for a model capability (e.g. thought_level)."""

    id: str
    label: str


class ModelChoice(BaseModel):
    """Model metadata advertised to the homepage model picker."""

    provider: str
    model: str
    label: str
    is_default: bool = False
    thought_levels: list[ModelOption] = Field(default_factory=list)
    default_thought_level: str | None = None


class CreateAppPayload(BaseModel):
    """HTTP payload submitted from the builder homepage to launch a Factory App."""

    prompt: str = ""
    name: str | None = None
    repo: str | None = None
    branch: str | None = None
    template: AppTemplateKind = "nextjs"
    web_app: bool | None = None
    mobile_app: bool = False
    vm: bool = True
    memory: int | None = 1
    testing: bool = False
    full_clone: bool = False
    t3: bool = True
    no_t3_persist: bool = False
    t3_usage_volume: str = DEFAULT_T3_USAGE_VOLUME
    t3_port: int = DEFAULT_T3_PORT
    t3_ssh_host: str | None = None
    metro_port: int = DEFAULT_METRO_PORT
    modal: bool = True
    sops: bool = True
    browser: bool = False
    react_native: bool = False
    no_cloudflare: bool = True
    xfce: bool = False
    xfce_port: int = DEFAULT_XFCE_PORT
    xfce_password: str | None = None
    profile: str | None = None
    provider: str = DEFAULT_BUILDER_PROVIDER
    model: str = DEFAULT_BUILDER_MODEL
    thought_level: str | None = None

    @model_validator(mode="after")
    def _validate_inputs(self) -> CreateAppPayload:
        self.prompt = (self.prompt or "").strip()
        self.repo = self.repo.strip() if self.repo and self.repo.strip() else None
        self.branch = self.branch.strip() if self.branch and self.branch.strip() else None
        self.name = self.name.strip() if self.name and self.name.strip() else None
        self.t3_ssh_host = self.t3_ssh_host.strip() if self.t3_ssh_host and self.t3_ssh_host.strip() else None
        self.xfce_password = self.xfce_password.strip() if self.xfce_password and self.xfce_password.strip() else None
        self.t3_usage_volume = (self.t3_usage_volume or DEFAULT_T3_USAGE_VOLUME).strip() or DEFAULT_T3_USAGE_VOLUME
        if self.repo is None and not self.prompt:
            raise ValueError("Prompt must not be empty.")
        if not self.t3:
            raise ValueError("T3 Code Server must remain enabled for Builder.")
        if self.xfce:
            self.vm = True
        if not self.vm:
            if "memory" in self.model_fields_set and self.memory is not None:
                raise ValueError("--memory can only be used with VM Sandbox mode.")
            self.memory = None
        elif self.memory is not None and self.memory < 1:
            raise ValueError("--memory must be at least 1 GB.")
        return self

    def resolved_web_app(self) -> bool:
        """Returns explicit web_app choice, or defaults to True only for scratch Next.js apps."""
        if self.web_app is not None:
            return self.web_app
        return self.repo is None and self.template == "nextjs"


class LaunchStep(BaseModel):
    """Single progress stage shown during Launch Request provisioning."""

    key: LaunchStatus
    label: str
    status: Literal["pending", "active", "done", "error"] = "pending"


class FactoryAppRecord(BaseModel):
    """Persistent state for a Factory App linking prompt/repo, workspace, sandbox, and T3 thread."""

    app_id: str
    slug: str
    title: str
    prompt: str = ""
    repo: str | None = None
    branch: str | None = None
    worktree_branch: str | None = None
    workspace_path: str | None = None
    repo_base_path: str | None = None
    template: AppTemplateKind = "nextjs"
    web_app: bool = True
    mobile_app: bool = False
    vm: bool = True
    memory: int | None = 1
    testing: bool = False
    full_clone: bool = False
    t3: bool = True
    no_t3_persist: bool = False
    t3_usage_volume: str = DEFAULT_T3_USAGE_VOLUME
    t3_port: int = DEFAULT_T3_PORT
    t3_ssh_host: str | None = None
    metro_port: int = DEFAULT_METRO_PORT
    modal: bool = True
    sops: bool = True
    browser: bool = False
    react_native: bool = False
    no_cloudflare: bool = True
    xfce: bool = False
    xfce_port: int = DEFAULT_XFCE_PORT
    xfce_password: str | None = None
    profile: str | None = None
    provider_instance_id: str | None = None
    provider: str = DEFAULT_BUILDER_PROVIDER
    model: str = DEFAULT_BUILDER_MODEL
    thought_level: str | None = None
    status: Literal["provisioning", "ready", "failed"] = "provisioning"
    latest_request_id: str | None = None
    failed_step: LaunchStatus | None = None
    workspace_ready: bool = False
    sandbox_id: str | None = None
    sandbox_name: str | None = None
    environment_id: str | None = None
    project_id: str | None = None
    thread_id: str | None = None
    t3_url: str | None = None
    chat_url: str | None = None
    database_name: str | None = None
    dev_port: int | None = None
    prime_key: str | None = None
    last_error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class FactoryAppView(FactoryAppRecord):
    """Factory App projection enriched with live sandbox state and matching snapshots."""

    runtime_status: Literal["provisioning", "running", "stopped", "failed"] = "provisioning"
    snapshot_image_id: str | None = None
    snapshot_name: str | None = None


class PrimeSandboxRecord(BaseModel):
    """Persistent state for an active multi-app Prime Sandbox keyed by capability tuple."""

    prime_key: str
    profile: str | None = None
    vm: bool = False
    mobile_app: bool = False
    status: PrimeStatus = "provisioning"
    owner_request_id: str | None = None
    sandbox_id: str | None = None
    sandbox_name: str | None = None
    t3_url: str | None = None
    environment_id: str | None = None
    next_port: int = DEFAULT_APP_BASE_PORT
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class PrimeSandboxView(PrimeSandboxRecord):
    """Prime Sandbox projection enriched with live runtime status and hosted app count."""

    runtime_status: Literal["provisioning", "running", "stopped", "failed"] = "provisioning"
    app_count: int = 0
    app_ids: list[str] = Field(default_factory=list)


class LaunchRequestRecord(BaseModel):
    """Persistent state for a single idempotent Factory App Launch Request."""

    request_id: str
    app_id: str
    kind: Literal["create", "relaunch"] = "create"
    resume_from_step: LaunchStatus | None = None
    execution_started_at: str | None = None
    created_sandbox_id: str | None = None
    published_sandbox_id: str | None = None
    failed_step: LaunchStatus | None = None
    status: LaunchStatus = "queued"
    current_label: str = "Queued launch request"
    steps: list[LaunchStep] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)
    handoff_url: str | None = None
    handoff_expires_at: str | None = None
    error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    def with_appended_logs(self, lines: list[str]) -> LaunchRequestRecord:
        """Returns a copy with trimmed launch log history appended."""
        if not lines:
            return self
        return self.model_copy(update={"logs": [*self.logs, *lines][-MAX_LAUNCH_LOG_LINES:]})

    def with_stage(
        self,
        status: LaunchStatus,
        label: str,
        *,
        log_lines: list[str] | None = None,
        handoff_url: str | None = None,
        handoff_expires_at: str | None = None,
        error: str | None = None,
        failed_step: LaunchStatus | None = None,
    ) -> LaunchRequestRecord:
        """Returns a copy advancing step timeline, logs, and terminal handoff/error fields."""
        base_steps = self.steps or initial_launch_steps()
        next_steps = fail_launch_steps(base_steps) if status == "failed" else advance_launch_steps(base_steps, status)
        next_logs = [*self.logs, *(log_lines or [])][-MAX_LAUNCH_LOG_LINES:]
        return self.model_copy(
            update={
                "status": status,
                "current_label": label,
                "steps": next_steps,
                "logs": next_logs,
                "handoff_url": handoff_url if handoff_url is not None else self.handoff_url,
                "handoff_expires_at": handoff_expires_at if handoff_expires_at is not None else self.handoff_expires_at,
                "error": error,
                "failed_step": failed_step if status == "failed" else None,
            }
        )

    def scrub_expired_handoff(self) -> tuple[LaunchRequestRecord, bool]:
        """Clears a persisted #token= handoff URL once its 5-minute TTL has expired."""
        if self.handoff_url and self.handoff_expires_at and is_iso_expired(self.handoff_expires_at):
            return self.model_copy(update={"handoff_url": None}), True
        return self, False


class LaunchStatusResponse(BaseModel):
    """Response returned by GET /api/launches/{request_id}."""

    request: LaunchRequestRecord
    app: FactoryAppRecord | None = None


class OpenAppResponse(BaseModel):
    """Response returned by POST /api/apps/{app_id}/open."""

    app_id: str
    handoff_url: str
    chat_url: str


STEP_DEFINITIONS: tuple[tuple[LaunchStatus, str], ...] = (
    ("launching_sandbox", "Provisioning Modal sandbox"),
    ("scaffolding_workspace", "Preparing Git workspace"),
    ("waiting_t3", "Waiting for T3 Code Server"),
    ("starting_thread", "Starting agent thread & pairing"),
)

DEFAULT_ANTIGRAVITY_MODELS: list[ModelChoice] = [
    ModelChoice(
        provider="antigravity",
        model="gemini-4-hydrogen",
        label="Antigravity · Gemini 4 Hydrogen",
        is_default=True,
        thought_levels=[
            ModelOption(id="low", label="Low"),
            ModelOption(id="medium", label="Medium"),
            ModelOption(id="high", label="High"),
            ModelOption(id="xhigh", label="Extra"),
        ],
        default_thought_level="xhigh",
    ),
    ModelChoice(
        provider="antigravity",
        model="gemini-3.8-flash",
        label="Antigravity · Gemini 3.8 Flash",
        thought_levels=[
            ModelOption(id="low", label="Low"),
            ModelOption(id="medium", label="Medium"),
            ModelOption(id="high", label="High"),
        ],
        default_thought_level="high",
    ),
    ModelChoice(
        provider="antigravity",
        model="claude-sonnet-4-6",
        label="Antigravity · Claude Sonnet 4.6",
        thought_levels=[
            ModelOption(id="low", label="Low"),
            ModelOption(id="medium", label="Medium"),
            ModelOption(id="high", label="High"),
            ModelOption(id="xhigh", label="Extra"),
        ],
        default_thought_level="high",
    ),
]


def resolve_default_thought_level(
    provider: str,
    model: str,
    explicit: str | None = None,
) -> str | None:
    """Returns explicit thought_level when provided, else the catalog default for provider/model."""
    clean = (explicit or "").strip()
    if clean:
        return clean
    for choice in DEFAULT_ANTIGRAVITY_MODELS:
        if choice.provider == provider and choice.model == model:
            return choice.default_thought_level
    return None


def build_factory_app_record(
    payload: CreateAppPayload,
    *,
    app_id: str,
    request_id: str,
    repo_full: str | None,
) -> FactoryAppRecord:
    """Constructs a FactoryAppRecord from a validated CreateAppPayload and resolved repo."""
    slug = derive_app_slug(payload.prompt, payload.name, repo=repo_full)
    title = derive_app_title(payload.prompt, payload.name, repo=repo_full)
    profile = payload.profile or None
    web_app = payload.resolved_web_app()
    mobile_app = bool(payload.mobile_app) if (repo_full is None and payload.template == "nextjs") else False
    effective_vm = bool(payload.vm or payload.xfce)
    effective_rn = bool(payload.react_native or mobile_app)
    effective_memory = payload.memory if effective_vm else None
    provider = payload.provider or DEFAULT_BUILDER_PROVIDER
    model = payload.model or DEFAULT_BUILDER_MODEL
    thought_level = resolve_default_thought_level(provider, model, payload.thought_level)
    repo_base_path = shared_repo_base_dir(repo_full) if repo_full else None
    worktree_branch = derive_worktree_branch(slug, app_id) if repo_full else None
    prime_key = prime_compatibility_key_for_app(
        payload.model_copy(
            update={
                "profile": profile,
                "vm": effective_vm,
                "mobile_app": mobile_app,
                "react_native": effective_rn,
                "memory": effective_memory,
            }
        )
    )
    return FactoryAppRecord(
        app_id=app_id,
        slug=slug,
        title=title,
        prompt=payload.prompt,
        repo=repo_full,
        branch=payload.branch if repo_full else None,
        worktree_branch=worktree_branch,
        repo_base_path=repo_base_path,
        template=payload.template,
        web_app=web_app,
        mobile_app=mobile_app,
        vm=effective_vm,
        memory=effective_memory,
        testing=payload.testing,
        full_clone=payload.full_clone,
        t3=payload.t3,
        no_t3_persist=payload.no_t3_persist,
        t3_usage_volume=payload.t3_usage_volume,
        t3_port=payload.t3_port,
        t3_ssh_host=payload.t3_ssh_host,
        metro_port=payload.metro_port,
        modal=payload.modal,
        sops=payload.sops,
        browser=payload.browser,
        react_native=effective_rn,
        no_cloudflare=payload.no_cloudflare,
        xfce=payload.xfce,
        xfce_port=payload.xfce_port,
        xfce_password=payload.xfce_password,
        profile=profile,
        prime_key=prime_key,
        provider=provider,
        model=model,
        thought_level=thought_level,
        status="provisioning",
        latest_request_id=request_id,
    )


def initial_launch_steps(*, resume_from: LaunchStatus | None = None) -> list[LaunchStep]:
    """Builds the ordered Launch Request step list, pre-completing steps before resume_from."""
    order = [key for key, _ in STEP_DEFINITIONS]
    resume_idx = order.index(resume_from) if resume_from in order else 0
    return [
        LaunchStep(key=key, label=label, status="done" if i < resume_idx else "pending")
        for i, (key, label) in enumerate(STEP_DEFINITIONS)
    ]


def advance_launch_steps(steps: list[LaunchStep], active_key: LaunchStatus) -> list[LaunchStep]:
    """Marks steps prior to active_key as done and active_key as active (or all done on ready)."""
    order = [key for key, _ in STEP_DEFINITIONS]
    if active_key == "ready":
        return [s.model_copy(update={"status": "done"}) for s in steps]
    if active_key not in order:
        return steps
    active_idx = order.index(active_key)
    return [
        s.model_copy(update={"status": "done" if i < active_idx else ("active" if i == active_idx else "pending")})
        for i, s in enumerate(steps)
    ]


def fail_launch_steps(steps: list[LaunchStep]) -> list[LaunchStep]:
    """Marks the active (or final) Launch Request step as errored."""
    out: list[LaunchStep] = []
    marked = False
    for step in steps:
        if step.status == "active":
            out.append(step.model_copy(update={"status": "error"}))
            marked = True
        else:
            out.append(step)
    if not marked and out:
        out[-1] = out[-1].model_copy(update={"status": "error"})
    return out
