# Factory Testing Console for Test Organization Verification

**Status**: Accepted

To streamline verification and interactive observation of autonomous assembly lines against the canonical Test Organization (`software-factory-09-test`), we decided to introduce the **Factory Testing Console**—a lightweight, local developer web interface implemented with Python FastAPI, Jinja2, Tailwind CSS, and Server-Sent Events (SSE), superseding the previous strictly-CLI restriction for testing workflows.

## Considered Options

- **Retaining Strictly CLI Dispatcher (`factory/run.py`)**: Relying only on terminal flags and modal CLI streaming output. Rejected because inspecting multiple unblocked tickets across test fixtures, switching parameters, and visually correlating assembly line stage transitions (Planner, Coder, Deterministic Verifier, Reviewer) creates friction during rapid test verification.
- **Cloud-Deployed Serverless Web Dashboard on Modal (`modal.fastapi_endpoint`)**: Deploying the testing UI as a remote serverless endpoint on Modal. Rejected because it incurs cloud deployment latency, requires external ingress and authentication management, and introduces unnecessary network boundary complexity for developer workstations that already possess decrypted credentials.
- **Full-Stack TypeScript SPA with Node/Vite Build Chain**: Building a separate React/Vite dashboard alongside the Python backend. Rejected because it introduces dual-runtime build requirements (Node.js + pnpm) on the host control plane, conflicting with the single-language Python architecture of `factory/`.
- **Local Developer Web Service (FastAPI + Tailwind + SSE)**: Accepted because a local Python web console runs with zero build overhead, natively integrates with `factory.orchestrator` and `factory.spawner`, securely decrypts `secrets_org/software-factory-09-test/token` into memory via host `sops` without exposing credentials, and delivers sub-millisecond real-time terminal streaming and milestone stepper updates.

## Consequences

- The canonical term **Factory Testing Console** is incorporated into `CONTEXT.md`.
- A dedicated Python package `factory/ui/` provides the FastAPI application, in-memory job registry, GitHub discovery client, and SSE streaming endpoints.
- Developers can launch the console via `python -m factory.ui`, `python factory/ui/server.py`, or `python factory/run.py --ui` (defaulting to `http://127.0.0.1:3000`).
- The console dynamically queries GitHub API for member repositories under `software-factory-09-test` and inspects remote `.scratch/` trees for features and tickets, with full manual override capabilities.
- Live job execution is tracked in an in-memory registry, streaming logs over SSE, parsing stage transitions (`PREFLIGHT`, `PLANNER`, `CODER`, `VERIFIER`, `REVIEWER`, `COMPLETED`), and offering an immediate Cancel button that calls `modal.Sandbox.terminate()`.
- Production repository dispatch remains governed by the CLI Dispatcher; the console is specifically tailored for `software-factory-09-test` validation.

## Amendments

- **Port 3000 Default Alignment**: The default port was amended from `8080` to `3000` (with fallback to `PORT` environment variable) to align with standard sandbox web ingress per ADR 0021 (`https://3000.mahesh0.dev`), enabling zero-config access through Cloudflare Tunnel.
- **Frontend Build Chain Transition**: The zero-build restriction on the host control plane was superseded by ADR 0036 (`docs/adr/0036-vite-spa-for-factory-studio.md`), adopting a compiled Vite React SPA served statically by FastAPI to accommodate complex IDE UI state, virtualized terminal streams, and component modularity.


