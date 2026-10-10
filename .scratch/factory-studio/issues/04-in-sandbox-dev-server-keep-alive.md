# 04: In-Sandbox Dev Server Keep-Alive Daemon

**What to build:** The software factory container entrypoint and sandbox configuration keep the sandbox alive after the assembly line verification and review stages pass, running the target application's TanStack Start dev server (`pnpm dev --port 3000 --host 0.0.0.0`) in the background so that the live website remains continuously accessible for interactive preview via Cloudflare Tunnel at `https://3000.mahesh0.dev` until terminated or timed out.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Sandbox entrypoint detects when dev preview mode is enabled and successfully launches `pnpm dev --port 3000 --host 0.0.0.0` following verification passes.
- [ ] Container remains in an active serving keep-alive state instead of terminating immediately after pipeline completion.
- [ ] Dev server binds properly to port 3000 inside the container, routing out through Cloudflare Tunnel ingress at `https://3000.mahesh0.dev`.
- [ ] Emergency cancellation via `modal.Sandbox.terminate()` shuts down the dev server and cleans up resources immediately.
- [ ] Automated tests verify that post-verification dev server execution logic triggers correctly and supports idle keep-alive.
