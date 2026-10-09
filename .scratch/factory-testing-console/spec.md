# Spec: Factory Testing Console

Status: resolved

## Problem Statement

Testing and verifying the autonomous Software Factory assembly line against test repositories in the canonical Test Organization (`software-factory-09-test`) currently requires running `python factory/run.py` from the command line with multiple flags (`--testing`, `--project`, `--feature`, `--issue`, `--model`, `--vm`). Developers cannot easily discover which test repositories or tickets exist on remote branches without checking GitHub manually, and terminal log streams make it difficult to visualize high-level pipeline stage transitions (Pre-flight Guard, Planner Agent, Coder Agent, Deterministic Verifier, Reviewer Agent) or quickly cancel runaway sandboxes.

## Solution

The **Factory Testing Console** is an interactive, local developer web interface built on Python FastAPI, Jinja2, Tailwind CSS, and Server-Sent Events (SSE). It runs directly on the developer's workstation at `http://127.0.0.1:8080`, providing:
1. Dynamic discovery of repositories under `software-factory-09-test` using in-memory SOPS decryption of `secrets_org/software-factory-09-test/token`.
2. On-demand GitHub tree inspection of target repositories to auto-populate `.scratch/` feature slugs and unblocked tickets, alongside manual text fallbacks.
3. Interactive launch configuration controls: Feature slug, Issue ID, Model selection (`DeepSeek V4.1 Flash` vs. `MiMo-V2.6-Flash`), and VM Sandbox toggle.
4. An in-memory Job Registry running jobs asynchronously via `factory.orchestrator.dispatch_job` / `factory.spawner.create_factory_sandbox`.
5. Real-time log streaming via SSE (`/api/jobs/{job_id}/stream`) with automated regex stage pattern matching (`PREFLIGHT`, `PLANNER`, `CODER`, `VERIFIER`, `REVIEWER`, `COMPLETED`), an interactive stage progress stepper, and an immediate Cancel button calling `sandbox.terminate()`.
6. A session run history drawer displaying execution statuses, durations, and commit links.

## User Stories

1. As a software engineer, I want to run `python -m factory.ui` or `python factory/run.py --ui`, so that an interactive testing console opens in my browser.
2. As a tester, I want to see a populated list of test repositories in `software-factory-09-test` (e.g. `test1`, `test2`, `test3`), so that I don't have to look up repo names manually.
3. As a developer, I want to select a repo and see its available features and tickets from `.scratch/`, so that I can dispatch a test ticket with a single click.
4. As a developer, I want to watch the assembly line progress through visual stage badges (`Pre-flight` -> `Planner` -> `Coder` -> `Verifier` -> `Reviewer`) in real time alongside terminal logs.
5. As a factory operator, I want to click "Cancel" to immediately terminate a running Modal Sandbox if a test run goes off track.
6. As an engineer, I want the web interface to require no Node.js build steps or npm installations on my host, running purely in Python.

## Implementation Architecture

- **`factory/ui/github.py`**: In-memory decryption of `secrets_org/software-factory-09-test/token` via `sops -d`, caching GitHub API responses for org repos and remote repository `.scratch/` directory trees.
- **`factory/ui/registry.py`**: Thread-safe in-memory `JobRegistry` managing active and historical jobs, ring-buffered log lines, stage milestone regex parsing, and sandbox termination.
- **`factory/ui/app.py`**: FastAPI application exposing JSON endpoints (`/api/repos`, `/api/repos/{repo}/scratch`, `/api/jobs`, `/api/jobs/{id}/cancel`), SSE streaming endpoint (`/api/jobs/{id}/stream`), and serving Jinja2 template for `/`.
- **`factory/ui/server.py`**: CLI server entrypoint running Uvicorn on configurable host/port.
- **`factory/ui/templates/index.html`**: Clean split-pane layout with Tailwind CSS, HTMX/SSE log stream consumer, milestone progress stepper, and dark terminal viewer.
- **`factory/run.py`**: Extended with `--ui` argument to launch the console directly.
