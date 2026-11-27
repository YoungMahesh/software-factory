"""Domain classification, merging, and FastAPI routes for sandbox T3 Pairing URLs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from sandbox.apps._models import utc_now_iso
from sandbox.lifecycle import (
    _SANDBOX_METADATA_CACHE,
    lookup_sandbox,
    update_sandbox_t3_pair_url,
)

from ._probe import (
    T3_BASE_DIR,
    exec_json,
    persist_pairing_link,
    probe_active_pairing_ids_cli,
    probe_sandbox_t3_state,
    resolve_t3_origin,
)

DEFAULT_PAIRING_TTL = "24h"
DEFAULT_PAIRING_LABEL = "Dashboard Pairing"
FACTORY_HANDOFF_LABEL = "Factory App Handoff"

T3PairingLinkStatus = Literal["active", "used", "expired"]


class T3PairingLinkEntry(BaseModel):
    """Single Pairing URL record with availability status."""

    id: str | None = None
    url: str
    status: T3PairingLinkStatus
    label: str | None = None
    created_at: str | None = None
    expires_at: str | None = None


class SandboxT3LinksResponse(BaseModel):
    """Response payload for `GET /api/sandboxes/{sandbox_id}/t3-links`."""

    sandbox_id: str
    available: bool
    reason: str | None = None
    t3_url: str | None = None
    links: list[T3PairingLinkEntry] = Field(default_factory=list)


t3_pairing_router = APIRouter(tags=["t3-pairing"])


def _parse_iso_dt(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_token(url: str | None) -> str | None:
    if not url or "#token=" not in url:
        return None
    token = url.split("#token=", 1)[1].strip()
    return token or None


def _build_pairing_url(t3_url: str, token: str) -> str:
    return f"{t3_url.rstrip('/')}/pair#token={token}"


def _classify_link_status(
    *,
    entry_id: str | None,
    consumed_at: str | None,
    revoked_at: str | None,
    expires_at: str | None,
    now_dt: datetime,
    active_cli_ids: set[str] | None,
) -> T3PairingLinkStatus:
    """Computes `active`, `used`, or `expired` with `used` taking precedence."""
    if consumed_at:
        return "used"
    if revoked_at:
        return "expired"

    exp_dt = _parse_iso_dt(expires_at)
    if active_cli_ids is not None and entry_id:
        if entry_id in active_cli_ids:
            return "active"
        if exp_dt is not None and now_dt >= exp_dt:
            return "expired"
        return "used"

    if exp_dt is not None and now_dt >= exp_dt:
        return "expired"
    return "active"


def merge_pairing_records(
    sandbox_id: str,
    t3_url: str,
    probe: dict[str, Any],
    *,
    now_dt: datetime,
    active_cli_ids: set[str] | None,
) -> list[T3PairingLinkEntry]:
    """Merges SQLite, file, and in-memory pairing records into oldest-first entries."""
    excluded_ids: set[str] = set()
    excluded_tokens: set[str] = set()
    records_by_key: dict[str, dict[str, Any]] = {}
    key_order: list[str] = []
    id_to_key: dict[str, str] = {}
    token_to_key: dict[str, str] = {}

    def ingest(
        *,
        entry_id: str | None,
        token: str | None,
        url: str | None,
        label: str | None,
        created_at: str | None,
        expires_at: str | None,
        consumed_at: str | None = None,
        revoked_at: str | None = None,
        authoritative: bool = False,
    ) -> None:
        clean_id = str(entry_id).strip() if entry_id else None
        clean_token = (token or _extract_token(url) or "").strip() or None
        if not clean_token:
            return
        clean_label = str(label).strip() if isinstance(label, str) and label.strip() else None
        if clean_label == FACTORY_HANDOFF_LABEL:
            if clean_id:
                excluded_ids.add(clean_id)
            excluded_tokens.add(clean_token)
            return
        if (clean_id and clean_id in excluded_ids) or clean_token in excluded_tokens:
            return

        existing_key = (clean_id and id_to_key.get(clean_id)) or token_to_key.get(clean_token)
        if existing_key is None:
            existing_key = f"id:{clean_id}" if clean_id else f"tok:{clean_token}"
            records_by_key[existing_key] = {
                "id": clean_id,
                "token": clean_token,
                "url": _build_pairing_url(t3_url, clean_token),
                "label": clean_label,
                "created_at": created_at,
                "expires_at": expires_at,
                "consumed_at": consumed_at,
                "revoked_at": revoked_at,
                "seq": len(key_order),
            }
            key_order.append(existing_key)
        else:
            rec = records_by_key[existing_key]
            if clean_id and (authoritative or not rec["id"]):
                rec["id"] = clean_id
            if clean_label and (authoritative or not rec["label"]):
                rec["label"] = clean_label
            if created_at and (authoritative or not rec["created_at"]):
                rec["created_at"] = created_at
            if expires_at and (authoritative or not rec["expires_at"]):
                rec["expires_at"] = expires_at
            if consumed_at:
                rec["consumed_at"] = consumed_at
            if revoked_at:
                rec["revoked_at"] = revoked_at

        if clean_id:
            id_to_key[clean_id] = existing_key
        token_to_key[clean_token] = existing_key

    cached_url = (_SANDBOX_METADATA_CACHE.get(sandbox_id) or {}).get("t3_pair_url")
    if isinstance(cached_url, str):
        ingest(entry_id=None, token=None, url=cached_url, label="Launch Pairing", created_at=None, expires_at=None)

    boot_rec = probe.get("boot_record")
    if isinstance(boot_rec, dict):
        ingest(
            entry_id=boot_rec.get("id"),
            token=boot_rec.get("credential"),
            url=boot_rec.get("url"),
            label=boot_rec.get("label") or "Boot Pairing",
            created_at=boot_rec.get("created_at") or boot_rec.get("createdAt"),
            expires_at=boot_rec.get("expires_at") or boot_rec.get("expiresAt"),
        )

    for item in probe.get("saved_links") or []:
        if isinstance(item, dict):
            ingest(
                entry_id=item.get("id"),
                token=item.get("credential"),
                url=item.get("url"),
                label=item.get("label"),
                created_at=item.get("created_at") or item.get("createdAt"),
                expires_at=item.get("expires_at") or item.get("expiresAt"),
            )

    for row in probe.get("db_rows") or []:
        if isinstance(row, dict):
            ingest(
                entry_id=row.get("id"),
                token=row.get("credential"),
                url=None,
                label=row.get("label"),
                created_at=row.get("created_at"),
                expires_at=row.get("expires_at"),
                consumed_at=row.get("consumed_at"),
                revoked_at=row.get("revoked_at"),
                authoritative=True,
            )

    active_records = [
        records_by_key[k]
        for k in key_order
        if not (
            (records_by_key[k]["id"] and records_by_key[k]["id"] in excluded_ids)
            or records_by_key[k]["token"] in excluded_tokens
        )
    ]

    min_dt = datetime.min.replace(tzinfo=timezone.utc)
    active_records.sort(key=lambda r: (_parse_iso_dt(r.get("created_at")) or min_dt, r["seq"]))

    return [
        T3PairingLinkEntry(
            id=rec["id"],
            url=rec["url"],
            status=_classify_link_status(
                entry_id=rec["id"],
                consumed_at=rec["consumed_at"],
                revoked_at=rec["revoked_at"],
                expires_at=rec["expires_at"],
                now_dt=now_dt,
                active_cli_ids=active_cli_ids,
            ),
            label=rec["label"],
            created_at=rec["created_at"],
            expires_at=rec["expires_at"],
        )
        for rec in active_records
    ]


def list_sandbox_t3_links(
    sandbox_id: str,
    profile: str | None = None,
) -> SandboxT3LinksResponse:
    """Inspects a running sandbox and returns all recorded T3 Pairing URLs and statuses."""
    sb, _, error_msg = lookup_sandbox(sandbox_id, profile=profile)
    if sb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_msg or f"Sandbox '{sandbox_id}' not found.",
        )

    if sb.poll() is not None:
        return SandboxT3LinksResponse(
            sandbox_id=sandbox_id,
            available=False,
            reason="Sandbox is not running.",
            links=[],
        )

    probe = probe_sandbox_t3_state(sb)
    t3_url, unavailable_reason = resolve_t3_origin(sb, probe)
    if not t3_url:
        return SandboxT3LinksResponse(
            sandbox_id=sandbox_id,
            available=False,
            reason=unavailable_reason,
            links=[],
        )

    active_cli_ids: set[str] | None = None
    if not probe.get("db_readable") and (probe.get("boot_record") or probe.get("saved_links")):
        active_cli_ids = probe_active_pairing_ids_cli(sb)

    links = merge_pairing_records(
        sandbox_id,
        t3_url,
        probe,
        now_dt=datetime.now(timezone.utc),
        active_cli_ids=active_cli_ids,
    )
    return SandboxT3LinksResponse(
        sandbox_id=sandbox_id,
        available=True,
        t3_url=t3_url,
        links=links,
    )


def generate_sandbox_t3_link(
    sandbox_id: str,
    profile: str | None = None,
) -> T3PairingLinkEntry:
    """Mints a fresh 24h one-time Pairing URL inside the sandbox and appends it to history."""
    sb, _, error_msg = lookup_sandbox(sandbox_id, profile=profile)
    if sb is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_msg or f"Sandbox '{sandbox_id}' not found.",
        )

    if sb.poll() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot generate pairing link for a stopped sandbox.",
        )

    probe = probe_sandbox_t3_state(sb)
    t3_url, unavailable_reason = resolve_t3_origin(sb, probe)
    if not t3_url:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=unavailable_reason or "T3 Code Server is not running or tunnel unavailable.",
        )

    try:
        created = exec_json(
            sb,
            "t3", "auth", "pairing", "create",
            "--base-dir", T3_BASE_DIR,
            "--ttl", DEFAULT_PAIRING_TTL,
            "--label", DEFAULT_PAIRING_LABEL,
            "--json",
            timeout=30,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed generating T3 pairing link: {exc}",
        ) from exc

    if not isinstance(created, dict) or not created.get("credential"):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="T3 pairing CLI did not return a pairing credential.",
        )

    credential = str(created["credential"]).strip()
    link_id = str(created["id"]).strip() if created.get("id") else None
    label = str(created.get("label") or DEFAULT_PAIRING_LABEL).strip()
    expires_at = str(created["expiresAt"]).strip() if created.get("expiresAt") else None
    created_at = utc_now_iso()
    url = _build_pairing_url(t3_url, credential)

    persist_pairing_link(
        sb,
        sandbox_id,
        {
            "id": link_id,
            "credential": credential,
            "url": url,
            "label": label,
            "created_at": created_at,
            "expires_at": expires_at,
        },
    )

    update_sandbox_t3_pair_url(sandbox_id, url)
    return T3PairingLinkEntry(
        id=link_id,
        url=url,
        status="active",
        label=label,
        created_at=created_at,
        expires_at=expires_at,
    )


@t3_pairing_router.get("/api/sandboxes/{sandbox_id}/t3-links", response_model=SandboxT3LinksResponse)
def api_list_sandbox_t3_links(
    sandbox_id: str,
    profile: str | None = Query(None, description="Owning profile name"),
) -> SandboxT3LinksResponse:
    """Lists existing T3 Code Server Pairing URLs and availability for a sandbox."""
    return list_sandbox_t3_links(sandbox_id, profile=profile)


@t3_pairing_router.post("/api/sandboxes/{sandbox_id}/t3-links", response_model=T3PairingLinkEntry)
def api_generate_sandbox_t3_link(
    sandbox_id: str,
    profile: str | None = Query(None, description="Owning profile name"),
) -> T3PairingLinkEntry:
    """Generates a new 24h one-time T3 Code Server Pairing URL for a running sandbox."""
    return generate_sandbox_t3_link(sandbox_id, profile=profile)
