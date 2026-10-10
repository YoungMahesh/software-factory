# Factory Studio for Interactive Frontend Application Generation

**Status**: Accepted

To provide a conversational, prompt-driven developer experience similar to Lovable for building frontend applications, we decided to introduce **Factory Studio**—an interactive split-pane interface hosted alongside the Factory Testing Console on dedicated port 3010.

## Considered Options

- **Retaining Testing Console with Manual Parameter Forms**: Requiring the developer to manually enter milestone titles and issue numbers in the form. Rejected because it lacks conversational agility and rapid visual feedback for building new applications from scratch.
- **Separate Web Applications for Studio and Console**: Building a distinct application on another port for Studio. Rejected because it duplicates GitHub discovery, job registries, authentication, and SSE streaming infrastructure.
- **Unified Single-Page Interface (Port 3010) with Preview on Port 3000**: Accepted because hosting the Studio on port 3010 frees port 3000 exclusively for the sandbox's TanStack Start dev server routed through Cloudflare Ingress (`https://3000.mahesh0.dev`), while sharing authentication, job registries, and execution harnesses.

## Consequences

- The canonical term **Factory Studio** is incorporated into `CONTEXT.md`.
- Factory Studio runs on default port 3010 (overrideable via `PORT=3010`), protected by HTTP Basic Auth (`FACTORY_AUTH_USER`, `FACTORY_AUTH_PASS`).
- Target applications are based on TanStack Start initialized from canonical template repository `software-factory-09-test/tanstack-start-template`.
- Chat prompts are automatically converted into GitHub Milestones and Issues in `software-factory-09-test`, accumulating commits on `factory/<feature>` and creating Draft Feature PRs.
- In-sandbox entrypoint starts `pnpm dev --port 3000 --host 0.0.0.0` post-verification and maintains a serving keep-alive state for live iframe preview via `https://3000.mahesh0.dev`.
- A pre-flight LLM guard strictly rejects non-frontend feature requests (databases, backend APIs, external storage).
- A top navigation toggle allows instantaneous switching between Studio View and Console View within the same SPA.
