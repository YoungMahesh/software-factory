"""Preview state persistence for Factory Studio Database."""

import time
from typing import Any

from ._models import _row_to_preview_dict


class PreviewStorageMixin:
    """Provides preview state CRUD operations."""

    def save_preview(self, preview_dict: dict[str, Any]) -> None:
        """Inserts or updates preview state for a repository."""
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO previews (repo, branch, preview_url, status, stage, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(repo) DO UPDATE SET
                    branch=excluded.branch,
                    preview_url=excluded.preview_url,
                    status=excluded.status,
                    stage=excluded.stage,
                    updated_at=excluded.updated_at;
                """,
                (
                    preview_dict["repo"],
                    preview_dict.get("branch"),
                    preview_dict.get("preview_url"),
                    preview_dict.get("status", "IDLE"),
                    preview_dict.get("stage", "IDLE"),
                    preview_dict.get("updated_at", time.time()),
                ),
            )

    def get_preview(self, repo: str) -> dict[str, Any] | None:
        """Fetches preview state for a repository."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT repo, branch, preview_url, status, stage, updated_at
                FROM previews
                WHERE repo = ?;
                """,
                (repo,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return _row_to_preview_dict(row)

    def get_all_previews(self) -> list[dict[str, Any]]:
        """Retrieves all preview states."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT repo, branch, preview_url, status, stage, updated_at
                FROM previews
                ORDER BY updated_at DESC;
                """
            )
            rows = cur.fetchall()

        return [_row_to_preview_dict(row) for row in rows]
