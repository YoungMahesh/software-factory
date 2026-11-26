# ADR 0095: Scratchpad Ideas/Raw Split and Persisted Catalog Cache

**Status**: Accepted (amends [ADR 0093](0093-central-config-store-and-dashboard-scratchpad.md) and [ADR 0094](0094-serialized-factory-state-authority.md)).

The **Scratchpad** tab (`#scratchpad`) in the **Sandbox Web Dashboard** splits into two sub-tabs — **Ideas** and **Raw** — backed by separate directories in the **Central Config Store** (`github.com/${GH_ORG_NAME}/config`) and a persisted **Scratchpad Catalog Cache** on `factory-state-v1`.

## Context

Under [ADR 0093](0093-central-config-store-and-dashboard-scratchpad.md), Scratchpad mixed AI-refined ideas and raw saves into a single composer and committed both into `config/scratchpad/`. It also queried GitHub's Contents API on every dashboard load (`init()`), risking unnecessary GitHub API latency and rate-limit pressure unlike Builder's manual-refresh **Repository Catalog Cache** ([ADR 0091](0091-github-repo-picker-and-opt-in-web-app-mode.md)). Operators need an AI-free **Raw** capture path whose submissions commit verbatim directly to a separate directory, alongside fast cached browsing for both sections.

## Decisions

1. **Separate Top-Level Directories (`scratchpad/` and `raw/`)**:
   - **Ideas** continues storing AI-refined **Idea Notes** in `config/scratchpad/<slug>.md`, preserving all existing notes without migration. `Save Raw` is removed from the Ideas composer and AI review modal.
   - **Raw** stores **Raw Notes** in a sibling top-level directory `config/raw/<slug>.md` rather than nesting under `scratchpad/ideas/` and `scratchpad/raw/`.
   - Submitting in **Raw** never invokes AI and shows no confirmation modal: it derives `<slug>.md` (with `-2`, `-3` collision disambiguation) from an optional title or leading words and commits the exact UTF-8 textarea text verbatim without `# Title` normalization.

2. **Persisted Scratchpad Catalog Cache with Lazy Body Reads**:
   - Store the note index for both `scratchpad/` and `raw/` in `factory-state-v1` (via the **Factory State Authority**), matching **Repository Catalog Cache** semantics: dashboard loads read strictly from cache with zero GitHub API calls, and a single **Refresh** button in Scratchpad syncs both directories from GitHub.
   - Committing an **Idea Note** or **Raw Note** from the dashboard immediately updates the local cache (metadata and body).
   - Reading an existing uncached note fetches that single file's Markdown body from GitHub on click and caches it locally (invalidated when its `sha` changes on Refresh), supporting **GitHub ↗**, **Copy**, and **Use in Builder →** for both sections.

## Considered Options

- **Nest Directories as `scratchpad/ideas/` and `scratchpad/raw/`**: Rejected to avoid migrating existing `config/scratchpad/*.md` files and breaking existing paths.
- **Pre-fetch All Note Bodies on Refresh**: Rejected to keep Refresh fast as the number of notes grows; per-note lazy fetch on click keeps GitHub reads proportional to opened notes.
- **Query GitHub Live on Dashboard Load**: Rejected to align with **Repository Catalog Cache** and eliminate per-load GitHub API calls.

## Consequences

- Existing `config/scratchpad/*.md` notes remain valid **Idea Notes** with zero migration.
- Fresh deployments show an empty **Scratchpad Catalog Cache** until an operator clicks **Refresh** or commits a new note from the dashboard.
- Notes committed outside the dashboard (e.g., directly via Git) appear in the UI only after clicking **Refresh**.
