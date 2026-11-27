# ADR 0097: Shared Repo Worktrees, Builder Defaults, Rootfs Snapshot Size, and Scratchpad Delete

**Status**: Accepted (amends [ADR 0090](0090-prime-sandbox-multi-app-reuse.md), [ADR 0091](0091-github-repo-picker-and-opt-in-web-app-mode.md), [ADR 0095](0095-scratchpad-ideas-raw-split-and-catalog-cache.md), and [ADR 0096](0096-nextjs-sandbox-dashboard-and-bff.md)).

We standardize the **Sandbox Web Dashboard** branding, default **VM Sandbox** mode (`vm=True`, `memory=1` GB) and **Antigravity · Gemini 4 Hydrogen** `Thinking: Extra` (`xhigh`) across Builder while exposing full sandbox-creation options in Builder `Advanced`, isolate GitHub repository Builder conversations into per-conversation T3 Git worktrees sharing `/root/<bare-repo>`, automatically prune Factory App cards upon sandbox termination, record apparent rootfs snapshot sizes at capture time, and add Scratchpad note deletion.

## Context

Three usability and correctness gaps remained after the Next.js migration ([ADR 0096](0096-nextjs-sandbox-dashboard-and-bff.md)):

1. **Inconsistent branding and defaults**: UI headings, metadata, and Basic Auth realms still used `"Modal Sandbox Runner"` rather than the Glossary name **Sandbox Web Dashboard**; Builder defaulted to gVisor containers instead of **VM Sandbox** mode, left `Thinking: Default` instead of **Extra** (`xhigh`) on Gemini 4 Hydrogen, and hid most `LaunchRequest` options compared to `Launch Fresh Sandbox`.
2. **Duplicated repository clones and stale cards**: Opening the same GitHub repository twice in a Prime Sandbox cloned a full copy into `/root/<slug>` each time rather than creating per-conversation Git worktrees, ran dependency installation regardless of `web_app`, and kept stale Factory App cards after sandbox termination.
3. **Opaque snapshot footprint and missing Scratchpad cleanup**: Modal image and sandbox APIs do not expose deduplicated snapshot sizes, leaving `/snapshots` with no footprint indicator, and `/scratchpad` lacked a way to delete committed **Idea Notes** or **Raw Notes**.

## Decisions

1. **Canonical Title (`Sandbox Web Dashboard`) & Builder/Modal Defaults**:
   - Unify Next.js `<title>`, header `<h1>`, HTTP Basic Auth realms (`dashboard/` and `sandboxes/sandbox/web.py`), FastAPI app title, and docs to **`Sandbox Web Dashboard`**.
   - Default `vm=True` (`memory=1` GB) in both **Launch Fresh Sandbox** (no extra fields added) and **Builder**, copy checked capability defaults (`t3=True`, `modal=True`, `sops=True`), default `Thinking: Extra` (`xhigh`) for `antigravity`/`gemini-4-hydrogen` (`CreateAppPayload` and UI), and expose all sandbox-creation arguments (`testing`, `full_clone`, `browser`, `react_native`, `no_cloudflare` [default `True` for Prime Sandboxes], `no_t3_persist`, `t3_usage_volume`, `t3_port`, `t3_ssh_host`, `metro_port`, `xfce`, `xfce_port`, `xfce_password`) inside Builder's **Advanced** panel, partitioned into `prime_compatibility_key`.

2. **T3-Managed Git Worktrees for Shared GitHub Repositories**:
   - When `app.repo` is set, clone or fetch once into `/root/<bare-repo>`, inject Central Config Store secrets into `<repo>/.git/env-vault/` (which global `/root/.git-hooks/post-checkout` automatically copies into every new worktree), and register `/root/<bare-repo>` once as a T3 Project.
   - Invoke T3's `t3_thread_launch` via `/mcp` *without* an initial `message` using `workspaceStrategy: { type: "worktree", baseRef, branch }` so T3 creates the worktree first; wait for `worktreePath`, run `pnpm install` / `npm install` inside that worktree only when `web_app=True`, and then dispatch the prompt via `t3 thread send` (leaving the worktree idle when both prompt and `web_app` are unset). Scratch `Next.js App` and `Blank Git` workspaces remain on `/root/<slug>`.

3. **Automatic Factory App Card Pruning on Sandbox Termination**:
   - Remove the manual Delete (`X`) button from Builder Factory App cards.
   - Delete bound `FactoryAppRecord`s (and their `LaunchRequestRecord`s) automatically when `POST /api/sandboxes/{sandbox_id}/terminate` succeeds and during `GET /api/apps` when `sb.poll() is not None` or `modal.exception.NotFoundError` confirms termination. Keep `DELETE /api/apps/{app_id}` intact for API callers.

4. **Capture-Time Snapshot Rootfs Size**:
   - Because Modal's SDK (`ImageFromId`, `ImageBuildChainGet`, `SandboxInfo`) does not expose stored image sizes, run `df -B1 /` (fallback `df -Pk /`) inside `capture_sandbox_snapshot()` before calling `snapshot_filesystem()` and store `rootfs_bytes` in `sandbox-snapshots`. Display **Rootfs Size** in `/snapshots` (`—` for legacy snapshots) with a tooltip clarifying it measures apparent capture-time rootfs usage including shared base layers.

5. **Scratchpad Idea & Raw Note Deletion**:
   - Add `DELETE /api/scratchpad/notes/{filename}?section=ideas|raw` to delete the file on GitHub via `CentralConfigStore.delete()` and evict it from `Scratchpad Catalog Cache`, exposed with confirmation in `/scratchpad`.

## Considered Options

- **Pre-create Git worktrees manually in Python via `git worktree add`**: Rejected in favor of letting T3 Code's `t3_thread_launch` create and bind worktrees natively without racing initial prompts against `pnpm install`.
- **Query Modal Billing/Volume APIs for snapshot sizes or profile storage**: Deferred/skipped; Modal APIs do not expose per-snapshot compressed/deduplicated storage bytes.

## Consequences

- Multiple Builder conversations on the same GitHub repository reuse `/root/<bare-repo>` cleanly in isolated branches (`sf/<slug>-<suffix>`) with automatic `.env*` secret propagation and fast dependency installation gated on `web_app`.
- Builder cards vanish automatically once their underlying sandbox terminates, while sibling worktrees on an active Prime Sandbox remain independent on relaunch or API delete.
