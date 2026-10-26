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
                INSERT INTO previews (
                    repo, branch, preview_url, status, stage, updated_at,
                    snapshot_image_id, snapshot_commit_sha, snapshot_captured_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repo) DO UPDATE SET
                    branch=excluded.branch,
                    preview_url=excluded.preview_url,
                    status=excluded.status,
                    stage=excluded.stage,
                    updated_at=excluded.updated_at,
                    snapshot_image_id=COALESCE(excluded.snapshot_image_id, previews.snapshot_image_id),
                    snapshot_commit_sha=COALESCE(excluded.snapshot_commit_sha, previews.snapshot_commit_sha),
                    snapshot_captured_at=COALESCE(excluded.snapshot_captured_at, previews.snapshot_captured_at);
                """,
                (
                    preview_dict["repo"],
                    preview_dict.get("branch"),
                    preview_dict.get("preview_url"),
                    preview_dict.get("status", "IDLE"),
                    preview_dict.get("stage", "IDLE"),
                    preview_dict.get("updated_at", time.time()),
                    preview_dict.get("snapshot_image_id"),
                    preview_dict.get("snapshot_commit_sha"),
                    preview_dict.get("snapshot_captured_at"),
                ),
            )

    def save_snapshot_metadata(
        self,
        repo: str,
        snapshot_image_id: str,
        snapshot_commit_sha: str,
        captured_at: float | None = None,
    ) -> None:
        """Saves or updates snapshot metadata for a repository."""
        captured_time = captured_at if captured_at is not None else time.time()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO previews (
                    repo, status, stage, updated_at,
                    snapshot_image_id, snapshot_commit_sha, snapshot_captured_at
                )
                VALUES (?, 'IDLE', 'IDLE', ?, ?, ?, ?)
                ON CONFLICT(repo) DO UPDATE SET
                    snapshot_image_id=excluded.snapshot_image_id,
                    snapshot_commit_sha=excluded.snapshot_commit_sha,
                    snapshot_captured_at=excluded.snapshot_captured_at,
                    updated_at=excluded.updated_at;
                """,
                (
                    repo,
                    captured_time,
                    snapshot_image_id,
                    snapshot_commit_sha,
                    captured_time,
                ),
            )

    def get_snapshot_metadata(self, repo: str) -> dict[str, Any] | None:
        """Fetches snapshot metadata for a repository."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT repo, snapshot_image_id, snapshot_commit_sha, snapshot_captured_at
                FROM previews
                WHERE repo = ?;
                """,
                (repo,),
            )
            row = cur.fetchone()
            if not row:
                return None
            keys = row.keys() if hasattr(row, "keys") else ()
            image_id = row["snapshot_image_id"] if "snapshot_image_id" in keys else None
            if not image_id:
                return None
            return {
                "repo": row["repo"],
                "snapshot_image_id": image_id,
                "snapshot_commit_sha": row["snapshot_commit_sha"] if "snapshot_commit_sha" in keys else None,
                "snapshot_captured_at": row["snapshot_captured_at"] if "snapshot_captured_at" in keys else None,
            }

    def get_preview(self, repo: str) -> dict[str, Any] | None:
        """Fetches preview state for a repository."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT repo, branch, preview_url, status, stage, updated_at,
                       snapshot_image_id, snapshot_commit_sha, snapshot_captured_at
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
                SELECT repo, branch, preview_url, status, stage, updated_at,
                       snapshot_image_id, snapshot_commit_sha, snapshot_captured_at
                FROM previews
                ORDER BY updated_at DESC;
                """
            )
            rows = cur.fetchall()

        return [_row_to_preview_dict(row) for row in rows]
