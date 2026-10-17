"""Repository-wide telemetry aggregation queries and bottleneck metrics calculation."""

import json
import re
from typing import Any


def normalize_command(command: str) -> str:
    """Normalizes a shell command by stripping leading exports, sudo, and whitespace."""
    if not command:
        return ""
    clean = command.strip()
    clean = re.sub(r"^(?:export\s+[A-Za-z0-9_]+=\S*\s*&&?\s*)+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"^sudo\s+", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def classify_operation(command: str, stage: str = "", is_thinking: bool = False) -> str:
    """Classifies an operation into an infrastructure category matching frontend heuristics."""
    if is_thinking:
        return "LLM Thinking"

    cmd = normalize_command(command)

    # 1. Git / VCS
    if re.search(r"^git(?:\.exe)?(?:\s+.*)?$", cmd, re.IGNORECASE):
        return "Git / VCS"

    # 2. Package Install
    if (
        re.search(r"^(?:pnpm|npm|yarn|bun)\s+(?:install|add|i)\b", cmd, re.IGNORECASE)
        or re.search(r"^(?:pip|pip3|uv\s+pip)\s+install\b", cmd, re.IGNORECASE)
        or re.search(r"^poetry\s+(?:install|add)\b", cmd, re.IGNORECASE)
        or re.search(r"^cargo\s+(?:add|install)\b", cmd, re.IGNORECASE)
    ):
        return "Package Install"

    # 3. Build / Compile
    if (
        re.search(r"^(?:pnpm|npm|yarn|bun)\s+(?:run\s+)?build\b", cmd, re.IGNORECASE)
        or re.search(
            r"^(?:npx\s+|pnpm\s+dlx\s+)?(?:tsc|vite\s+build|webpack|esbuild|rollup|next\s+build|turbo\s+build)\b",
            cmd,
            re.IGNORECASE,
        )
        or re.search(r"^(?:cargo\s+build|make\b|gcc\b|g\+\+\b)", cmd, re.IGNORECASE)
    ):
        return "Build / Compile"

    # 4. Test Suite
    if (
        re.search(r"^(?:pnpm|npm|yarn|bun)\s+(?:run\s+)?test\b", cmd, re.IGNORECASE)
        or re.search(r"^(?:npx\s+|pnpm\s+dlx\s+)?(?:vitest|jest|pytest|playwright|cypress)\b", cmd, re.IGNORECASE)
        or re.search(r"^(?:python3?|py)\s+-m\s+pytest\b", cmd, re.IGNORECASE)
        or re.search(r"^(?:go|cargo)\s+test\b", cmd, re.IGNORECASE)
        or (stage and stage.upper() == "VERIFIER")
    ):
        return "Test Suite"

    return "Command"


class BottlenecksStorageMixin:
    """Provides repository-wide telemetry aggregation queries and bottleneck metrics."""

    def get_repo_bottlenecks(
        self,
        repo: str,
        limit: int | None = 50,
    ) -> list[dict[str, Any]]:
        """Queries persistent telemetry events across all past runs of a repository,

        grouping normalized commands and thinking phases to calculate cumulative execution time,
        invocation count, average duration, and maximum single-run duration.
        """
        clean_repo = (repo or "").strip()
        if not clean_repo:
            return []

        if hasattr(self, "flush_batches"):
            try:
                self.flush_batches()
            except Exception:
                pass

        with self._cursor() as cur:
            cur.execute(
                """
                SELECT e.id, e.job_id, e.seq, e.event_type, e.stage, e.data_json, e.created_at
                FROM job_telemetry_events e
                JOIN factory_jobs j ON e.job_id = j.id
                WHERE j.repo = ? AND e.event_type IN ('tool_result', 'thinking')
                ORDER BY e.job_id ASC, e.seq ASC, e.created_at ASC;
                """,
                (clean_repo,),
            )
            rows = cur.fetchall()

        if not rows:
            return []

        # Group rows by job_id for proper folding of thinking streams
        events_by_job: dict[str, list[Any]] = {}
        for r in rows:
            events_by_job.setdefault(r["job_id"], []).append(r)

        extracted_operations: list[dict[str, Any]] = []

        for job_id, job_rows in events_by_job.items():
            # 1. Fold thinking events by stage within the job
            thinking_blocks: list[dict[str, Any]] = []
            for r in job_rows:
                if r["event_type"] == "thinking":
                    stage = r["stage"]
                    data_obj = {}
                    if r["data_json"]:
                        try:
                            data_obj = json.loads(r["data_json"])
                        except Exception:
                            data_obj = {}
                    inner_data = data_obj.get("data") if isinstance(data_obj.get("data"), dict) else data_obj
                    stage = stage or data_obj.get("stage") or inner_data.get("stage")

                    last = thinking_blocks[-1] if thinking_blocks else None
                    if last and last.get("stage") == stage and not last.get("done"):
                        if inner_data.get("durationMs") is not None:
                            last["durationMs"] = inner_data["durationMs"]
                        if inner_data.get("done") is not None:
                            last["done"] = bool(inner_data["done"])
                    else:
                        thinking_blocks.append({
                            "stage": stage,
                            "durationMs": inner_data.get("durationMs"),
                            "done": bool(inner_data.get("done")),
                        })

            for tb in thinking_blocks:
                dur = tb.get("durationMs")
                if dur is not None and dur >= 0:
                    stage_name = tb.get("stage") or "Agent"
                    title = f"LLM Thinking ({stage_name})"
                    extracted_operations.append({
                        "command": title,
                        "durationMs": dur,
                        "stage": stage_name,
                        "category": "LLM Thinking",
                    })

            # 2. Extract tool_result operations
            for r in job_rows:
                if r["event_type"] == "tool_result":
                    data_obj = {}
                    if r["data_json"]:
                        try:
                            data_obj = json.loads(r["data_json"])
                        except Exception:
                            data_obj = {}
                    inner_data = data_obj.get("data") if isinstance(data_obj.get("data"), dict) else data_obj

                    tool_name = (inner_data.get("toolName") or data_obj.get("toolName") or "").lower()
                    stage = r["stage"] or inner_data.get("stage") or data_obj.get("stage") or ""
                    is_bash = tool_name == "bash"
                    is_verifier = stage.upper() == "VERIFIER"

                    raw_cmd = (
                        inner_data.get("command")
                        or inner_data.get("args", {}).get("command")
                        or data_obj.get("command")
                        or ""
                    )

                    if is_bash or is_verifier or raw_cmd:
                        cmd = raw_cmd or tool_name or "bash"
                        norm_cmd = normalize_command(cmd)
                        if norm_cmd:
                            dur = inner_data.get("durationMs")
                            if dur is None:
                                dur = data_obj.get("durationMs", 0)
                            category = classify_operation(norm_cmd, stage=stage, is_thinking=False)
                            extracted_operations.append({
                                "command": norm_cmd,
                                "durationMs": dur,
                                "stage": stage or "CODER",
                                "category": category,
                            })

        # Group extracted operations by normalized command
        groups: dict[str, list[dict[str, Any]]] = {}
        for op in extracted_operations:
            groups.setdefault(op["command"], []).append(op)

        aggregated: list[dict[str, Any]] = []
        for cmd, ops in groups.items():
            durations = [o["durationMs"] for o in ops]
            total_dur = sum(durations)
            count = len(durations)
            avg_dur = round(total_dur / count, 1) if count > 0 else 0.0
            max_dur = max(durations) if durations else 0

            # Determine dominant stage
            stages = [o["stage"] for o in ops if o.get("stage")]
            dominant_stage = max(set(stages), key=stages.count) if stages else "CODER"
            category = ops[0]["category"]

            aggregated.append({
                "command": cmd,
                "category": category,
                "stage": dominant_stage,
                "count": count,
                "invocation_count": count,
                "total_duration_ms": total_dur,
                "total_time": total_dur,
                "avg_duration_ms": avg_dur,
                "avg_time": avg_dur,
                "max_duration_ms": max_dur,
                "max_time": max_dur,
            })

        # Sort strictly in descending order of total_duration_ms
        aggregated.sort(key=lambda x: (x["total_duration_ms"], x["count"]), reverse=True)

        if limit is not None and limit > 0:
            return aggregated[:limit]
        return aggregated
