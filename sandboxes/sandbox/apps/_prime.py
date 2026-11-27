"""Prime Sandbox provisioning coordination, reuse, port allocation, and app cleanup."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Any, Callable, Literal

import modal

from sandbox.core import LaunchRequest, LaunchResponse

from ._models import (
    FactoryAppRecord,
    LaunchRequestRecord,
    LaunchStatus,
    prime_compatibility_key_for_app,
    prime_sandbox_app_name,
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
    is_prime_owner: bool
    t3_meta: dict[str, Any] | None = None
    resume_step: LaunchStatus | None = None
    reused_app_sandbox: bool = False


def is_prime_sandbox_id(store: FactoryStateStore, sandbox_id: str | None) -> bool:
    """Identifies shared containers, including preserved app attachments."""
    return bool(sandbox_id and (
        any(p.sandbox_id == sandbox_id for p in store.list_primes())
        or any(a.sandbox_id == sandbox_id and a.prime_key is not None for a in store.list_apps())
    ))


def has_sibling_repo_app(store: FactoryStateStore, app: FactoryAppRecord) -> bool:
    """Returns True when another app on the same sandbox shares app.repo_base_path."""
    if not (app.sandbox_id and app.repo_base_path):
        return False
    return any(
        other.app_id != app.app_id
        and other.sandbox_id == app.sandbox_id
        and other.repo_base_path == app.repo_base_path
        for other in store.list_apps()
    )


def probe_sandbox_liveness(
    client_for_profile_fn: Callable[[str], Any],
    sandbox_from_id_fn: Callable[..., Any],
    sandbox_id: str | None,
    profile: str | None,
) -> Literal["running", "terminated", "unknown"]:
    """Checks whether a sandbox is alive, confirmed terminated/missing, or transiently unreachable."""
    if not sandbox_id:
        return "unknown"
    try:
        client = client_for_profile_fn(profile) if profile else None
        sb = sandbox_from_id_fn(sandbox_id, client=client) if client else sandbox_from_id_fn(sandbox_id)
    except modal.exception.NotFoundError:
        return "terminated"
    except Exception:
        return "unknown"
    if sb is None:
        return "terminated"
    try:
        return "running" if sb.poll() is None else "terminated"
    except modal.exception.NotFoundError:
        return "terminated"
    except Exception:
        return "unknown"


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
    prime_key = app.prime_key or prime_compatibility_key_for_app(app)
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
                is_prime_owner=False,
                resume_step=resume_step,
                reused_app_sandbox=True,
            )

    deadline = time.monotonic() + wait_timeout_secs
    logged_waiting = False
    while True:
        assert_active()
        cur = store.claim_prime(app.app_id, launch.request_id, stale_secs=stale_secs)
        if cur.status == "ready" and cur.sandbox_id and cur.t3_url:
            sb = get_running_sandbox(cur.sandbox_id, app.profile)
            t3_meta = probe_t3_ready(sb) if sb is not None else None
            if t3_meta is not None:
                record_progress("launching_sandbox", "Attaching to Prime Sandbox",
                                f"Reusing active Prime Sandbox {cur.sandbox_id} (skipping container boot)...")
                return AcquiredSandbox(
                    sandbox=sb,
                    response=LaunchResponse(sandbox_id=cur.sandbox_id,
                        app_name=prime_sandbox_app_name(vm=app.vm, mobile_app=app.mobile_app),
                        sandbox_name=cur.sandbox_name or cur.sandbox_id, t3_url=cur.t3_url),
                    is_prime_owner=False, t3_meta=t3_meta,
                )
            store.mark_prime_stopped(cur.sandbox_id)
            continue
        if cur.owner_request_id == launch.request_id:
            break
        if not logged_waiting:
            record_progress("launching_sandbox", "Waiting for Prime Sandbox",
                            "Another prompt is booting the Prime Sandbox; waiting to attach...")
            logged_waiting = True
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Timed out waiting {int(wait_timeout_secs)}s for Prime Sandbox '{prime_key}'.")
        time.sleep(poll_interval_secs)

    record_progress(
        "launching_sandbox",
        "Provisioning Prime Sandbox",
        "No active Prime Sandbox found; starting fresh Modal sandbox...",
    )
    sb = None
    launch_resp = None
    try:
        effective_vm = bool(app.vm or app.xfce)
        effective_rn = bool(app.mobile_app or app.react_native)
        req = LaunchRequest(
            repo=None,
            testing=app.testing,
            full_clone=app.full_clone,
            name=prime_sandbox_app_name(vm=effective_vm, mobile_app=effective_rn),
            vm=effective_vm,
            memory=app.memory if effective_vm else None,
            no_cloudflare=app.no_cloudflare,
            t3=app.t3,
            t3_port=app.t3_port,
            t3_ssh_host=app.t3_ssh_host,
            t3_usage_volume=app.t3_usage_volume,
            no_t3_persist=no_t3_persist or app.no_t3_persist,
            react_native=effective_rn,
            metro_port=app.metro_port,
            modal=app.modal,
            profile=app.profile,
            sops=app.sops,
            browser=app.browser,
            xfce=app.xfce,
            xfce_port=app.xfce_port,
            xfce_password=app.xfce_password,
        )
        running = launch_fn(req, log_cb=log_cb)
        sb, launch_resp = (running.sandbox, running.response) if hasattr(running, "response") else running
        if not launch_resp.t3_url:
            raise RuntimeError("Modal sandbox did not expose a T3 Code Server tunnel URL.")
        if not store.bind_prime_sandbox(prime_key, launch.request_id, launch_resp.sandbox_id,
                                       launch_resp.sandbox_name, launch_resp.t3_url):
            raise RuntimeError("Prime Sandbox provisioning claim was lost during sandbox launch.")
    except Exception:
        if launch_resp is not None:
            terminate_quietly(launch_resp.sandbox_id, profile=app.profile, reason="prime_acquisition_failure")
        try:
            store.release_prime_claim(prime_key, launch.request_id)
        except Exception:
            logger.exception("Failed releasing Prime Sandbox claim after acquisition failure")
        raise

    return AcquiredSandbox(
        sandbox=sb,
        response=launch_resp,
        is_prime_owner=True,
    )
