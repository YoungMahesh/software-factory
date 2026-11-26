"""Domain schemas, slug derivation, URL builders, and prompt helpers for Factory Apps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
from typing import Literal
from urllib.parse import quote

from pydantic import BaseModel, Field, field_validator

DEFAULT_BUILDER_PROVIDER = "antigravity"
DEFAULT_BUILDER_MODEL = "gemini-4-hydrogen"

MAX_SLUG_LENGTH = 42
MAX_TITLE_LENGTH = 60
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

AppTemplateKind = Literal["nextjs", "blank"]


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


def _sanitize_slug(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    if not cleaned:
        cleaned = "factory-app"
    if cleaned[0].isdigit():
        cleaned = f"app-{cleaned}"
    return cleaned[:MAX_SLUG_LENGTH].rstrip("-") or "factory-app"


def derive_app_slug(
    prompt: str,
    explicit_name: str | None = None,
    existing_slugs: set[str] | None = None,
) -> str:
    """Derives a unique filesystem/sandbox-safe slug from explicit_name or prompt."""
    if explicit_name and explicit_name.strip():
        base = _sanitize_slug(explicit_name.strip())
    else:
        first_line = next((line.strip() for line in prompt.splitlines() if line.strip()), "")
        words = re.findall(r"[a-zA-Z0-9]+", first_line)[:5]
        base = _sanitize_slug("-".join(words)) if words else "factory-app"

    used = existing_slugs or set()
    if base not in used:
        return base

    suffix_num = 2
    while True:
        suffix = f"-{suffix_num}"
        candidate = f"{base[:MAX_SLUG_LENGTH - len(suffix)].rstrip('-')}{suffix}"
        if candidate not in used:
            return candidate
        suffix_num += 1


def derive_app_title(prompt: str, explicit_name: str | None = None) -> str:
    """Derives a concise single-line title from explicit_name or the prompt's first line."""
    raw = explicit_name.strip() if explicit_name and explicit_name.strip() else ""
    if not raw:
        raw = next((line.strip() for line in prompt.splitlines() if line.strip()), "Untitled App")
    raw = re.sub(r"\s+", " ", raw)
    if len(raw) <= MAX_TITLE_LENGTH:
        return raw
    return raw[: MAX_TITLE_LENGTH - 3].rstrip() + "..."


def build_initial_thread_prompt(raw_prompt: str, *, template: AppTemplateKind, app_dir: str) -> str:
    """Appends the one-time run-app instruction to the prompt submitted to T3."""
    clean_prompt = raw_prompt.strip()
    if template == "nextjs":
        suffix = (
            f"Once built and verified in {app_dir}, use the run-app workflow: "
            "run `pnpm run dev` and open its localhost URL in the T3 Code browser so the live preview is open."
        )
    else:
        suffix = (
            f"Workspace is initialized at {app_dir}. Once built, start the local web server "
            "and open its localhost URL in the T3 Code browser so the live preview is open."
        )
    return f"{clean_prompt}\n\n{suffix}"


def build_direct_chat_url(
    t3_url: str,
    environment_id: str,
    thread_id: str,
    token: str | None = None,
) -> str:
    """Builds the direct T3 Web chat route, optionally attaching a one-time pairing fragment."""
    base = (
        f"{t3_url.rstrip('/')}/"
        f"{quote(environment_id, safe='')}/"
        f"{quote(thread_id, safe='')}"
    )
    if token:
        return f"{base}#token={quote(token, safe='')}"
    return base


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

    prompt: str
    name: str | None = None
    template: AppTemplateKind = "nextjs"
    mobile_app: bool = False
    vm: bool = False
    profile: str | None = None
    provider: str = DEFAULT_BUILDER_PROVIDER
    model: str = DEFAULT_BUILDER_MODEL
    thought_level: str | None = None

    @field_validator("prompt")
    @classmethod
    def _validate_prompt(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Prompt must not be empty.")
        return stripped


class LaunchStep(BaseModel):
    """Single progress stage shown during Launch Request provisioning."""

    key: LaunchStatus
    label: str
    status: Literal["pending", "active", "done", "error"] = "pending"


class FactoryAppRecord(BaseModel):
    """Persistent state for a Factory App linking prompt, workspace, sandbox, and T3 thread."""

    app_id: str
    slug: str
    title: str
    prompt: str
    template: AppTemplateKind = "nextjs"
    mobile_app: bool = False
    vm: bool = False
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
    last_error: str | None = None
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


class FactoryAppView(FactoryAppRecord):
    """Factory App projection enriched with live sandbox state and matching snapshots."""

    runtime_status: Literal["provisioning", "running", "stopped", "failed"] = "provisioning"
    snapshot_image_id: str | None = None
    snapshot_name: str | None = None


class LaunchRequestRecord(BaseModel):
    """Persistent state for a single idempotent Factory App Launch Request."""

    request_id: str
    app_id: str
    kind: Literal["create", "relaunch"] = "create"
    resume_from_step: LaunchStatus | None = None
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
    ("scaffolding_workspace", "Preparing local Git workspace"),
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
        default_thought_level="high",
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
