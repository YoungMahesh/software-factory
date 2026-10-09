# Issue 03: FastAPI Application and SSE Endpoints

Status: resolved

## Objective
Implement `factory/ui/app.py` with FastAPI endpoints to serve the UI, fetch repositories and `.scratch/` trees, launch test jobs, stream logs via SSE, and cancel running jobs.

## Acceptance Criteria
- `GET /`: Renders main testing console page using Jinja2 templates.
- `GET /api/repos`: Returns list of repositories under `software-factory-09-test`.
- `GET /api/repos/{repo}/scratch`: Returns discovered features and tickets for the specified repository.
- `POST /api/jobs`: Validates launch parameters, registers a new job, starts background execution, and returns `job_id`.
- `GET /api/jobs`: Returns list of all session jobs with current status and stages.
- `GET /api/jobs/{job_id}/stream`: Streams real-time SSE events (`log`, `stage`, `status`).
- `POST /api/jobs/{job_id}/cancel`: Requests sandbox termination.
