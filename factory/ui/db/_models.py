"""Data models and row converters for Factory Studio Database."""

import sqlite3
from typing import Any


def _row_to_job_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "repo": row["repo"],
        "feature": row["feature"],
        "issue": row["issue"],
        "model": row["model"],
        "vm": bool(row["vm"]),
        "dev": bool(row["dev"]),
        "preview_url": row["preview_url"],
        "status": row["status"],
        "stage": row["stage"],
        "exit_code": row["exit_code"],
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
    }


def _row_to_preview_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "repo": row["repo"],
        "branch": row["branch"],
        "preview_url": row["preview_url"],
        "status": row["status"],
        "stage": row["stage"],
        "updated_at": row["updated_at"],
    }
