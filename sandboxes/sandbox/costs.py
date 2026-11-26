"""Per-sandbox Modal cost estimation with TTL caching and fallback querying.

Uses `sb._experimental_stats()` (`SandboxGetStatsRequest`) as the primary source
because it queries directly by `sandbox_id`, works without `app_id` or custom
tags, and has no 7-day UTC-hour window restriction. Falls back to public
`App.sandboxes.stats()` when `_experimental_stats` is unavailable or unsupported
(for example on persistent sandboxes) and the sandbox has `app_name`,
`created_at`, and `instance_name` tags.

Why not `Workspace.billing.report()`? Modal's workspace billing report aggregates
at the App (`ap-...`) level and omits partial final intervals, so it cannot
attribute live accrued spend to individual sandboxes.

Why a separate `/api/sandboxes/costs` endpoint? Keeping cost lookup off
`GET /api/sandboxes` prevents ~1s/sandbox Modal stats RPCs from blocking the
5-second liveness poll and preserves existing CLI/API contracts.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import threading
import time
from typing import Any, Literal

from fastapi import APIRouter, Query
import modal
from pydantic import BaseModel, Field

from sandbox.apps._models import utc_now_iso
from sandbox.profiles import get_active_profile_name, get_all_clients, get_client_for_profile

logger = logging.getLogger(__name__)

DEFAULT_COST_CACHE_TTL_SECONDS = 60.0
DEFAULT_MAX_WORKERS = 6
_APP_STATS_MAX_RANGE = timedelta(days=7)

CostSource = Literal["sandbox_stats", "app_stats", "unavailable"]


class SandboxCostEntry(BaseModel):
    """Estimated accrued Modal usage cost and resource breakdown for one sandbox."""

    sandbox_id: str
    profile: str | None = None
    cost_usd: float | None = None
    cost_by_resource_usd: dict[str, float] = Field(default_factory=dict)
    duration_seconds: float | None = None
    billed_cpu_core_seconds: float | None = None
    billed_memory_gib_seconds: float | None = None
    since: str | None = None
    until: str | None = None
    source: CostSource = "unavailable"
    cached: bool = False
    error: str | None = None


class SandboxCostsResponse(BaseModel):
    """Response payload returned by `GET /api/sandboxes/costs`."""

    fetched_at: str
    costs: dict[str, SandboxCostEntry] = Field(default_factory=dict)


_COST_CACHE_LOCK = threading.Lock()
_COST_CACHE: dict[str, tuple[float, SandboxCostEntry]] = {}

costs_router = APIRouter(tags=["sandbox-costs"])


def clear_sandbox_cost_cache(sandbox_id: str | None = None) -> None:
    """Clears cached sandbox cost entries for one sandbox or the entire cache."""
    with _COST_CACHE_LOCK:
        if sandbox_id:
            _COST_CACHE.pop(sandbox_id, None)
        else:
            _COST_CACHE.clear()


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (Decimal, int, float)):
        return round(float(value), 8)
    return None


def _to_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    return None


def _parse_utc_datetime(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_resource_costs(raw_map: Any) -> dict[str, float]:
    if not isinstance(raw_map, dict):
        return {}
    out: dict[str, float] = {}
    for key, raw_val in raw_map.items():
        num = _to_float(raw_val)
        if num is not None:
            out[str(key)] = num
    return out


def _fetch_via_experimental_stats(sb: Any, profile_name: str | None) -> SandboxCostEntry:
    stats_fn = getattr(sb, "_experimental_stats", None)
    if not callable(stats_fn):
        raise AttributeError("_experimental_stats is unavailable on sandbox handle")
    stats = stats_fn()
    duration_td = getattr(stats, "duration", None)
    duration_seconds = round(duration_td.total_seconds(), 3) if isinstance(duration_td, timedelta) else None
    return SandboxCostEntry(
        sandbox_id=sb.object_id,
        profile=profile_name,
        cost_usd=_to_float(getattr(stats, "cost", None)),
        cost_by_resource_usd=_extract_resource_costs(getattr(stats, "cost_by_resource", None)),
        duration_seconds=duration_seconds,
        billed_cpu_core_seconds=_to_float(getattr(stats, "billed_cpu_core_seconds", None)),
        billed_memory_gib_seconds=_to_float(getattr(stats, "billed_memory_gib_seconds", None)),
        since=_to_iso(getattr(stats, "since", None)),
        until=_to_iso(getattr(stats, "until", None)),
        source="sandbox_stats",
        cached=False,
        error=None,
    )


def _fetch_via_app_stats_fallback(
    sb: Any,
    client: modal.Client,
    profile_name: str | None,
) -> SandboxCostEntry:
    tags = sb.get_tags() if hasattr(sb, "get_tags") else {}
    if not isinstance(tags, dict):
        tags = {}

    app_name = tags.get("app_name")
    created_raw = tags.get("created_at")
    instance_name = tags.get("instance_name")
    created_dt = _parse_utc_datetime(created_raw)

    if not (app_name and created_raw and instance_name and created_dt):
        return SandboxCostEntry(
            sandbox_id=sb.object_id,
            profile=profile_name,
            source="unavailable",
            error="Sandbox lacks tags required for App.sandboxes.stats fallback",
        )

    app = modal.App.lookup(app_name, client=client)
    now_utc = datetime.now(timezone.utc)
    cursor = created_dt.replace(minute=0, second=0, microsecond=0)
    if cursor >= now_utc:
        cursor = now_utc.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)

    filter_tags = {"instance_name": instance_name, "created_at": created_raw}
    group_keys = ["instance_name", "created_at"]

    total_cost = Decimal("0")
    by_resource: dict[str, Decimal] = {}
    saw_group = False

    while cursor < now_utc:
        window_end = min(cursor + _APP_STATS_MAX_RANGE, now_utc)
        until_arg = window_end if window_end < now_utc else None
        for group in app.sandboxes.stats(
            since=cursor,
            until=until_arg,
            tags=filter_tags,
            group_by_tags=group_keys,
        ):
            saw_group = True
            group_cost = getattr(group, "cost", None)
            if isinstance(group_cost, Decimal):
                total_cost += group_cost
            for res_name, res_cost in (getattr(group, "cost_by_resource", None) or {}).items():
                if isinstance(res_cost, Decimal):
                    by_resource[str(res_name)] = by_resource.get(str(res_name), Decimal("0")) + res_cost
        if until_arg is None:
            break
        cursor = window_end

    return SandboxCostEntry(
        sandbox_id=sb.object_id,
        profile=profile_name,
        cost_usd=round(float(total_cost), 8) if saw_group else None,
        cost_by_resource_usd={k: round(float(v), 8) for k, v in by_resource.items()},
        since=created_dt.isoformat(),
        until=now_utc.isoformat(),
        source="app_stats",
        cached=False,
        error=None,
    )


def fetch_sandbox_cost(sb: Any, client: modal.Client, profile_name: str | None) -> SandboxCostEntry:
    """Queries accrued Modal cost for a single sandbox handle with safe fallback."""
    try:
        return _fetch_via_experimental_stats(sb, profile_name)
    except (AttributeError, NotImplementedError) as exc:
        logger.debug("Falling back to App.sandboxes.stats for %s: %s", getattr(sb, "object_id", "?"), exc)
        try:
            return _fetch_via_app_stats_fallback(sb, client, profile_name)
        except Exception as fallback_exc:
            logger.warning(
                "Fallback cost lookup failed for %s (%s): %s",
                getattr(sb, "object_id", "?"),
                profile_name,
                fallback_exc,
            )
            return SandboxCostEntry(
                sandbox_id=sb.object_id,
                profile=profile_name,
                source="unavailable",
                error=str(fallback_exc),
            )
    except Exception as exc:
        logger.warning(
            "Failed querying stats for sandbox %s (%s): %s",
            getattr(sb, "object_id", "?"),
            profile_name,
            exc,
        )
        return SandboxCostEntry(
            sandbox_id=sb.object_id,
            profile=profile_name,
            source="unavailable",
            error=str(exc),
        )


def _list_profile_sandboxes(
    client: modal.Client,
    profile_name: str,
    app_name: str | None,
    all_apps: bool,
) -> list[Any]:
    target_app = app_name
    if not all_apps and target_app is None:
        target_app = "software-factory"

    app_id = None
    if target_app and not all_apps:
        try:
            app = modal.App.lookup(target_app, client=client)
            app_id = app.app_id
        except Exception as exc:
            logger.debug("App '%s' not found for profile '%s': %s", target_app, profile_name, exc)
            return []

    try:
        gen = modal.Sandbox.list(app_id=app_id, client=client) if app_id else modal.Sandbox.list(client=client)
        return list(gen)
    except Exception as exc:
        logger.warning("Failed listing sandboxes for cost lookup under profile '%s': %s", profile_name, exc)
        return []


def _resolve_profile_clients(profile: str | None) -> list[tuple[str, modal.Client]]:
    if profile == "all":
        return list(get_all_clients().items())
    target_profile = profile or get_active_profile_name()
    try:
        client = get_client_for_profile(target_profile)
        return [(target_profile or "default", client)]
    except Exception as exc:
        logger.error("Failed resolving client for profile '%s': %s", target_profile, exc)
        return []


def get_sandbox_costs(
    *,
    app_name: str | None = None,
    all_apps: bool = True,
    profile: str | None = None,
    refresh: bool = False,
    sandbox_ids: list[str] | None = None,
    ttl_seconds: float = DEFAULT_COST_CACHE_TTL_SECONDS,
    max_workers: int = DEFAULT_MAX_WORKERS,
) -> SandboxCostsResponse:
    """Returns cached or freshly queried per-sandbox Modal costs across matching profiles."""
    id_filter = set(sandbox_ids) if sandbox_ids else None
    results: dict[str, SandboxCostEntry] = {}
    pending: list[tuple[Any, modal.Client, str]] = []
    now_mono = time.monotonic()

    for prof_name, client in _resolve_profile_clients(profile):
        for sb in _list_profile_sandboxes(client, prof_name, app_name, all_apps):
            sb_id = getattr(sb, "object_id", None)
            if not sb_id or (id_filter is not None and sb_id not in id_filter):
                continue

            cached_entry: SandboxCostEntry | None = None
            if not refresh:
                with _COST_CACHE_LOCK:
                    item = _COST_CACHE.get(sb_id)
                    if item is not None and (now_mono - item[0]) < ttl_seconds:
                        cached_entry = item[1].model_copy(update={"cached": True})

            if cached_entry is not None:
                results[sb_id] = cached_entry
            else:
                pending.append((sb, client, prof_name))

    if pending:
        workers = max(1, min(max_workers, len(pending)))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [(sb.object_id, executor.submit(fetch_sandbox_cost, sb, client, prof)) for sb, client, prof in pending]
            for sb_id, future in futures:
                try:
                    entry = future.result()
                except Exception as exc:
                    entry = SandboxCostEntry(sandbox_id=sb_id, source="unavailable", error=str(exc))
                results[sb_id] = entry
                if entry.error is None:
                    with _COST_CACHE_LOCK:
                        _COST_CACHE[sb_id] = (time.monotonic(), entry)

    return SandboxCostsResponse(fetched_at=utc_now_iso(), costs=results)


@costs_router.get("/api/sandboxes/costs", response_model=SandboxCostsResponse)
def api_list_sandbox_costs(
    app_name: str | None = Query(None, description="Filter by app name"),
    all_apps: bool = Query(True, description="Scan environment-wide without scoping to an App"),
    profile: str | None = Query(None, description="Profile name or 'all' for aggregated across profiles"),
    refresh: bool = Query(False, description="Bypass cost cache and query Modal directly"),
    sandbox_ids: list[str] | None = Query(None, description="Optional sandbox ID filter"),
) -> SandboxCostsResponse:
    """Returns accrued Modal compute/memory cost for active sandboxes."""
    effective_all_apps = all_apps if app_name is None else False
    return get_sandbox_costs(
        app_name=app_name,
        all_apps=effective_all_apps,
        profile=profile,
        refresh=refresh,
        sandbox_ids=sandbox_ids,
    )
