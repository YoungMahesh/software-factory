# Compiled Vite SPA for Factory Studio and Testing Console

**Status**: Accepted (Amends ADR 0032 and ADR 0034)

To support long-term UI complexity (virtualized log streams, interactive diff viewers, multi-turn chat state, and drawer synchronizations) without monolithic template maintainability issues, we decided to evolve the frontend architecture from a single Jinja2 HTML monolith to a **Compiled Vite React SPA**, statically served by FastAPI.

## Considered Options

- **Retaining Zero-Build Monolith (`factory/ui/templates/index.html`)**: Keeping all HTML, CSS, and vanilla JS in a single Jinja template. Rejected because the file grew beyond 3,100 lines, mixing imperative DOM manipulation, SSE subscriptions, and layout markup, creating high maintenance friction and cognitive overload for developers and AI agents.
- **Full-Stack TanStack Start SSR**: Running an independent Node.js SSR process on port 3010. Rejected because backend sandbox orchestration, SOPS secret decryption, and job lifecycle logic must remain in Python (`modal`, `sops`). Running dual full-stack servers (Node SSR + FastAPI) introduces redundant server daemons, CORS/proxy latency, and packaging friction.
- **Compiled Vite React SPA served by FastAPI**: Accepted because it provides the full declarative power and typed component ecosystem of React (TanStack Router, TanStack Query, Radix UI primitives, Lucide icons, virtualized terminal streams) during development, while compiling down to static assets (`factory/ui/static/dist/`) served directly by the single FastAPI Uvicorn process on port 3010 in production and CLI dispatch.

## Consequences

- ADR 0032 is amended: the host environment permits a Node.js 24 + pnpm 10 build toolchain for frontend development, while production runtime remains a single-process Python FastAPI application serving pre-compiled static assets.
- A dedicated frontend workspace is established under `factory/ui/frontend/` with Vite, React 19, TypeScript, Tailwind CSS, TanStack Router, and TanStack Query.
- FastAPI (`factory/ui/app.py`) mounts static asset serving for `factory/ui/static/dist/` and serves `index.html` for client-side routing.
- Existing REST endpoints (`/api/repos`, `/api/jobs`, `/api/studio/prompt`) and SSE streams (`/api/jobs/{id}/stream`) remain unchanged, serving as the stable contract for the React SPA.
