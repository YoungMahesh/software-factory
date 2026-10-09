# Issue 02: In-Memory Job Registry and Stage Detector

Status: resolved

## Objective
Implement `factory/ui/registry.py` to maintain active and historical software factory test runs in memory. Manage background worker execution, capture stdout/stderr streams into a ring buffer, parse pipeline milestones via regular expressions, and provide a mechanism to cancel running sandboxes.

## Acceptance Criteria
- Thread-safe `JobRegistry` with status tracking (`QUEUED`, `RUNNING`, `SUCCESS`, `FAILED`, `CANCELLED`).
- Detects stages: `PREFLIGHT`, `PLANNER`, `CODER`, `VERIFIER`, `REVIEWER`, `COMPLETE`.
- Exposes real-time event generator suitable for Server-Sent Events (SSE).
- Supports terminating active sandboxes via `sandbox.terminate()`.
