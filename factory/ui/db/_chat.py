"""Chat message persistence for Factory Studio Database."""

import json
import time
from typing import Any
import uuid


class ChatStorageMixin:
    """Provides chat messages CRUD and rollback history persistence."""

    def save_chat_message(
        self,
        repo: str,
        role: str,
        content: str,
        milestone_slug: str | None = None,
        issue_number: int | None = None,
        turn_data: dict[str, Any] | None = None,
        message_id: str | None = None,
        created_at: float | None = None,
    ) -> dict[str, Any]:
        """Saves a conversational chat message and returns its serialized representation."""
        msg_id = message_id or str(uuid.uuid4())
        ts = created_at if created_at is not None else time.time()
        turn_data_json = json.dumps(turn_data) if turn_data is not None else None

        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO chat_messages (id, repo, milestone_slug, issue_number, role, content, turn_data_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    repo=excluded.repo,
                    milestone_slug=excluded.milestone_slug,
                    issue_number=excluded.issue_number,
                    role=excluded.role,
                    content=excluded.content,
                    turn_data_json=excluded.turn_data_json,
                    created_at=excluded.created_at;
                """,
                (msg_id, repo, milestone_slug, issue_number, role, content, turn_data_json, ts),
            )

        return {
            "id": msg_id,
            "repo": repo,
            "milestone_slug": milestone_slug,
            "issue_number": issue_number,
            "role": role,
            "content": content,
            "turn_data": turn_data,
            "created_at": ts,
        }

    def get_chat_messages(self, repo: str) -> list[dict[str, Any]]:
        """Retrieves chronological chat messages for a repository."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, repo, milestone_slug, issue_number, role, content, turn_data_json, created_at
                FROM chat_messages
                WHERE repo = ?
                ORDER BY created_at ASC;
                """,
                (repo,),
            )
            rows = cur.fetchall()

        messages = []
        for r in rows:
            turn_data = None
            if r["turn_data_json"]:
                try:
                    turn_data = json.loads(r["turn_data_json"])
                except Exception:
                    turn_data = None

            draft_adr = turn_data.get("draft_adr") if isinstance(turn_data, dict) else None

            messages.append(
                {
                    "id": r["id"],
                    "repo": r["repo"],
                    "milestone_slug": r["milestone_slug"],
                    "issue_number": r["issue_number"],
                    "role": r["role"],
                    "content": r["content"],
                    "turn_data": turn_data,
                    "draft_adr": draft_adr,
                    "created_at": r["created_at"],
                }
            )
        return messages

    def mark_chat_message_reverted(
        self,
        message_id: str,
        revert_commit: str | None = None,
    ) -> dict[str, Any] | None:
        """Marks a chat message as reverted with timestamp and revert commit SHA."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT id, repo, milestone_slug, issue_number, role, content, turn_data_json, created_at
                FROM chat_messages
                WHERE id = ?;
                """,
                (message_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            turn_data: dict[str, Any] = {}
            if row["turn_data_json"]:
                try:
                    loaded = json.loads(row["turn_data_json"])
                    if isinstance(loaded, dict):
                        turn_data = loaded
                except Exception:
                    turn_data = {}

            now = time.time()
            turn_data["reverted"] = True
            turn_data["reverted_at"] = now
            if revert_commit is not None:
                turn_data["revert_commit"] = revert_commit

            turn_data_json = json.dumps(turn_data)
            cur.execute(
                """
                UPDATE chat_messages
                SET turn_data_json = ?
                WHERE id = ?;
                """,
                (turn_data_json, message_id),
            )

        return {
            "id": row["id"],
            "repo": row["repo"],
            "milestone_slug": row["milestone_slug"],
            "issue_number": row["issue_number"],
            "role": row["role"],
            "content": row["content"],
            "turn_data": turn_data,
            "created_at": row["created_at"],
        }

    def save_rollback_message(
        self,
        repo: str,
        original_message_id: str | None = None,
        original_commit_sha: str | None = None,
        revert_commit_sha: str | None = None,
        issue_number: int | str | None = None,
        branch: str | None = None,
        content: str | None = None,
    ) -> dict[str, Any]:
        """Persists an append-only turn rollback event to chat messages."""
        if content is None:
            issue_str = f" for Issue #{issue_number}" if issue_number is not None else ""
            orig_sha_display = original_commit_sha or "unknown"
            revert_sha_display = revert_commit_sha or "unknown"
            content = f"↩️ Rolled back turn{issue_str} (commit {orig_sha_display} ➔ {revert_sha_display}). Live Preview restored to previous version."

        turn_data: dict[str, Any] = {
            "type": "turn_rollback",
            "original_message_id": original_message_id,
            "original_commit_sha": original_commit_sha,
            "revert_commit_sha": revert_commit_sha,
            "issue_number": issue_number,
            "branch": branch,
        }

        parsed_issue_num: int | None = None
        if issue_number is not None:
            try:
                parsed_issue_num = int(issue_number)
            except (ValueError, TypeError):
                parsed_issue_num = None

        return self.save_chat_message(
            repo=repo,
            role="assistant",
            content=content,
            issue_number=parsed_issue_num,
            turn_data=turn_data,
        )

    def delete_chat_messages(self, repo: str) -> int:
        """Deletes chat messages for a repository while keeping jobs and logs."""
        with self._cursor() as cur:
            cur.execute("DELETE FROM chat_messages WHERE repo = ?;", (repo,))
            return cur.rowcount
