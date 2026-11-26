"""Prime Sandbox provisioning coordination, reuse, port allocation, and app cleanup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import time
from typing import Any, Callable

from sandbox.core import LaunchRequest, LaunchResponse

from ._models import (
    DEFAULT_APP_BASE_PORT,
    FactoryAppRecord,
    LaunchRequestRecord,
    LaunchStatus,
    PrimeSandboxRecord,
    PrimeStatus,
    prime_compatibility_key,
    prime_sandbox_app_name,
    utc_now_iso,
)
from ._sandbox_t3 import probe_t3_ready
from ._store import FactoryStateStore

logger = logging.getLogger(__name__)

PRIME_WAIT_TIMEOUT_SECS = 300.0
PRIME_PROVISION_STALE_SECS = 420.0
PRIME_POLL_INTERVAL_SECS = 1.0


@dataclass(frozen=True)
class AcquiredSandbox:
    """Result of acquiring an existing Prime Sandbox or booting a fresh one."""

    sandbox: Any
    response: LaunchResponse
    prime_key: str
    reused_prime: bool
    is_prime_owner: bool
    t3_meta: dict[str, Any] | None = None
    resume_step: LaunchStatus | None = None
    reused_app_sandbox: bool = False


def _is_timestamp_stale(timestamp: str | None, max_age_secs: float) -> bool:
    if not timestamp:
        return True
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return True
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed).total_seconds() >= max_age_secs


def _is_provisioning_owner_dead(
    store: FactoryStateStore,
    prime: PrimeSandboxRecord,
    stale_secs: float,
) -> bool:
    if not prime.owner_request_id:
        return True
    owner_launch = store.get_launch(prime.owner_request_id, reload=False)
    if owner_launch is None or owner_launch.status in ("failed", "ready"):
        return True
    owner_app = store.get_app(owner_launch.app_id, reload=False)
    if owner_app is None or owner_app.latest_request_id != prime.owner_request_id:
        return True
    return _is_timestamp_stale(prime.updated_at, stale_secs)


def is_prime_sandbox_id(store: FactoryStateStore, sandbox_id: str | None) -> bool:
    """Returns True when sandbox_id is tracked as a Prime Sandbox or hosts Prime apps."""
    if not sandbox_id:
        return False
    if any(p.sandbox_id == sandbox_id for p in store.list_primes()):
        return True
    return any(a.sandbox_id == sandbox_id and a.prime_key is not None for a in store.list_apps())


def mark_prime_stopped(store: FactoryStateStore, sandbox_id: str | None) -> None:
    """Marks any matching PrimeSandboxRecord as stopped when its container terminates."""
    if not sandbox_id:
        return
    for prime in store.list_primes():
        if prime.sandbox_id == sandbox_id and prime.status in ("ready", "provisioning"):
            store.modify_prime(
                prime.prime_key,
                lambda cur, sid=sandbox_id: (
                    cur.model_copy(update={"status": "stopped"})
                    if cur is not None and cur.sandbox_id == sid
                    else None
                ),
            )


def release_prime_claim(
    store: FactoryStateStore,
    prime_key: str,
    request_id: str,
    *,
    status: PrimeStatus = "failed",
) -> None:
    """Releases an in-flight provisioning claim owned by request_id."""
    store.modify_prime(
        prime_key,
        lambda cur: (
            cur.model_copy(update={"status": status, "owner_request_id": None})
            if cur is not None and cur.owner_request_id == request_id and cur.status == "provisioning"
            else None
        ),
    )


def mark_prime_ready(
    store: FactoryStateStore,
    prime_key: str,
    *,
    request_id: str,
    sandbox_id: str,
    sandbox_name: str | None,
    t3_url: str,
    environment_id: str,
) -> PrimeSandboxRecord | None:
    """Marks an active Prime Sandbox ready once T3 Code Server readiness succeeds."""
    return store.modify_prime(
        prime_key,
        lambda cur: (
            (
                cur.model_copy(
                    update={
                        "status": "ready",
                        "owner_request_id": None,
                        "sandbox_id": sandbox_id,
                        "sandbox_name": sandbox_name,
                        "t3_url": t3_url,
                        "environment_id": environment_id,
                    }
                )
                if cur is not None
                and (cur.owner_request_id == request_id or cur.sandbox_id == sandbox_id or cur.status != "ready")
                else (
                    PrimeSandboxRecord(
                        prime_key=prime_key,
                        status="ready",
                        sandbox_id=sandbox_id,
                        sandbox_name=sandbox_name,
                        t3_url=t3_url,
                        environment_id=environment_id,
                        next_port=DEFAULT_APP_BASE_PORT,
                    )
                    if cur is None
                    else None
                )
            )
        ),
    )


def allocate_dev_port(
    store: FactoryStateStore,
    prime_key: str,
    sandbox_id: str,
    *,
    request_id: str | None = None,
) -> int:
    """Atomically allocates a unique monotonically increasing dev port on the target sandbox."""
    allocated: dict[str, int] = {}

    def _bump(cur: PrimeSandboxRecord | None) -> PrimeSandboxRecord | None:
        if cur is None:
            return None
        matches_sb = cur.sandbox_id == sandbox_id
        matches_owner = bool(request_id and cur.owner_request_id == request_id and cur.status == "provisioning")
        if not (matches_sb or matches_owner):
            return None
        port = max(cur.next_port, DEFAULT_APP_BASE_PORT)
        allocated["port"] = port
        return cur.model_copy(update={"next_port": port + 1})

    store.modify_prime(prime_key, _bump)
    if "port" in allocated:
        return allocated["port"]

    used_ports = [
        app.dev_port
        for app in store.list_apps()
        if app.sandbox_id == sandbox_id and app.dev_port is not None
    ]
    return max(used_ports, default=DEFAULT_APP_BASE_PORT - 1) + 1


def acquire_sandbox_for_app(
    *,
    store: FactoryStateStore,
    app: FactoryAppRecord,
    launch: LaunchRequestRecord,
    resumable_steps: tuple[LaunchStatus, ...],
    get_running_sandbox: Callable[[str | None, str | None], Any | None],
    launch_fn: Callable[..., Any],
    terminate_quietly: Callable[..., None],
    no_t3_persist: bool,
    log_cb: Callable[[str], None] | None = None,
    record_progress: Callable[[LaunchStatus, str, str | None], None],
    assert_active: Callable[[], None],
    wait_timeout_secs: float = PRIME_WAIT_TIMEOUT_SECS,
    poll_interval_secs: float = PRIME_POLL_INTERVAL_SECS,
    stale_secs: float = PRIME_PROVISION_STALE_SECS,
) -> AcquiredSandbox:
    """Resumes an app's preserved sandbox, reuses an active Prime Sandbox, or provisions one."""
    prime_key = app.prime_key or prime_compatibility_key(app.profile, app.vm, app.mobile_app)
    resume_step = launch.resume_from_step
    if resume_step in resumable_steps and app.sandbox_id and app.t3_url:
        existing_sb = get_running_sandbox(app.sandbox_id, app.profile)
        if existing_sb is not None:
            resp = LaunchResponse(
                sandbox_id=app.sandbox_id,
                app_name=app.slug,
                sandbox_name=app.sandbox_name or app.slug,
                t3_url=app.t3_url,
            )
            record_progress(
                resume_step,
                "Resuming on active sandbox",
                f"Reusing active sandbox {app.sandbox_id}; resuming from {resume_step}...",
            )
            return AcquiredSandbox(
                sandbox=existing_sb,
                response=resp,
                prime_key=prime_key,
                reused_prime=True,
                is_prime_owner=False,
                resume_step=resume_step,
                reused_app_sandbox=True,
            )

    deadline = time.monotonic() + wait_timeout_secs
    logged_waiting = False
    while True:
        assert_active()
        cur = store.get_prime(prime_key)

        if cur is not None and cur.status == "ready" and cur.sandbox_id and cur.t3_url:
            sb = get_running_sandbox(cur.sandbox_id, app.profile)
            if sb is not None:
                t3_meta = probe_t3_ready(sb)
                if t3_meta is not None:
                    record_progress(
                        "launching_sandbox",
                        "Attaching to Prime Sandbox",
                        f"Reusing active Prime Sandbox {cur.sandbox_id} (skipping container boot)...",
                    )
                    resp = LaunchResponse(
                        sandbox_id=cur.sandbox_id,
                        app_name=prime_sandbox_app_name(vm=app.vm, mobile_app=app.mobile_app),
                        sandbox_name=cur.sandbox_name or cur.sandbox_id,
                        t3_url=cur.t3_url,
                    )
                    return AcquiredSandbox(
                        sandbox=sb,
                        response=resp,
                        prime_key=prime_key,
                        reused_prime=True,
                        is_prime_owner=False,
                        t3_meta=t3_meta,
                    )
            dead_id = cur.sandbox_id
            store.modify_prime(
                prime_key,
                lambda p, expected_id=dead_id: (
                    p.model_copy(update={"status": "stopped"})
                    if p is not None and p.sandbox_id == expected_id and p.status == "ready"
                    else None
                ),
            )
            continue

        if cur is not None and cur.status == "provisioning":
            if cur.owner_request_id == launch.request_id:
                break
            if _is_provisioning_owner_dead(store, cur, stale_secs):
                stale_owner = cur.owner_request_id
                claimed = store.modify_prime(
                    prime_key,
                    lambda p, prev_owner=stale_owner: (
                        PrimeSandboxRecord(
                            prime_key=prime_key,
                            profile=app.profile,
                            vm=app.vm,
                            mobile_app=app.mobile_app,
                            status="provisioning",
                            owner_request_id=launch.request_id,
                            next_port=DEFAULT_APP_BASE_PORT,
                        )
                        if p is None or (p.status == "provisioning" and p.owner_request_id == prev_owner)
                        else None
                    ),
                )
                if claimed is not None and claimed.owner_request_id == launch.request_id:
                    break
                continue
            if not logged_waiting:
                record_progress(
                    "launching_sandbox",
                    "Waiting for Prime Sandbox",
                    "Another prompt is booting the Prime Sandbox; waiting to attach...",
                )
                logged_waiting = True
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Timed out waiting {int(wait_timeout_secs)}s for Prime Sandbox '{prime_key}'."
                )
            time.sleep(poll_interval_secs)
            continue

        claimed = store.modify_prime(
            prime_key,
            lambda p: (
                PrimeSandboxRecord(
                    prime_key=prime_key,
                    profile=app.profile,
                    vm=app.vm,
                    mobile_app=app.mobile_app,
                    status="provisioning",
                    owner_request_id=launch.request_id,
                    next_port=DEFAULT_APP_BASE_PORT,
                    updated_at=utc_now_iso(),
                )
                if p is None or p.status in ("failed", "stopped")
                else None
            ),
        )
        if claimed is not None and claimed.owner_request_id == launch.request_id:
            break

    record_progress(
        "launching_sandbox",
        "Provisioning Prime Sandbox",
        "No active Prime Sandbox found; starting fresh Modal sandbox...",
    )
    sb = None
    launch_resp = None
    try:
        req = LaunchRequest(
            repo=None,
            name=prime_sandbox_app_name(vm=app.vm, mobile_app=app.mobile_app),
            vm=app.vm,
            no_cloudflare=True,
            t3=True,
            no_t3_persist=no_t3_persist,
            react_native=app.mobile_app,
            modal=False,
            profile=app.profile,
        )
        running = launch_fn(req, log_cb=log_cb)
        sb, launch_resp = (running.sandbox, running.response) if hasattr(running, "response") else running
        if not launch_resp.t3_url:
            terminate_quietly(launch_resp.sandbox_id, profile=app.profile, reason="missing_t3_url")
            raise RuntimeError("Modal sandbox did not expose a T3 Code Server tunnel URL.")
    except Exception:
        release_prime_claim(store, prime_key, launch.request_id, status="failed")
        raise

    return AcquiredSandbox(
        sandbox=sb,
        response=launch_resp,
        prime_key=prime_key,
        reused_prime=False,
        is_prime_owner=True,
    )
