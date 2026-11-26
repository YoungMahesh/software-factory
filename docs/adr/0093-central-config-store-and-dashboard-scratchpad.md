# ADR 0093: Central Config Store (`config`) and Dashboard Scratchpad

**Status**: Accepted (Supersedes [ADR 0057](0057-central-env-store-and-host-side-secret-injection.md) and [ADR 0086](0086-host-ingress-store-for-opt-caddy.md) repository naming; amends [ADR 0065](0065-retire-in-repo-env-map-and-standardize-ghclone-on-env-store.md), [ADR 0066](0066-multi-tier-git-identity-and-env-store-separation.md), [ADR 0067](0067-git-worktree-environment-propagation-and-central-env-map.md), [ADR 0089](0089-prompt-homepage-and-t3-launch-coordinator.md), and [ADR 0091](0091-github-repo-picker-and-opt-in-web-app-mode.md))

## Context

Software Factory previously maintained two separate private operational repositories under `${GH_ORG_NAME}`: `env-store` for SOPS-encrypted environment secrets (`<repo>/...`) and `caddy-store` for Host Ingress Proxy backups (`<profile>/...`). Splitting factory configuration across multiple small private repositories increased organizational clutter and required keeping both repositories out of the dashboard repository picker.

Separately, operators using the **Sandbox Web Dashboard** often want to capture rough feature ideas or architectural plans in a persistent **Scratchpad** and ask AI to structure them into clean Markdown before either committing them to versioned storage (`scratchpad/`) or launching a **Factory App** build in the Builder tab, without requiring paid subscriptions or API credits on the control plane.

## Decision

1. **Unified Private `config` Repository (**Central Config Store**)**:
   - Consolidate `env-store` and `caddy-store` (with Git history preserved) into a single canonical private GitHub repository `github.com/${GH_ORG_NAME}/config` partitioned by top-level directory:
     - `env/<repo>/`: SOPS-encrypted `.env` / mapped secret files, `env.map`, and `git.env` resolved by `EnvStoreVault`, `push-repo-env`, `pull-repo-env`, and `ghclone`.
     - `caddy/<profile>/`: Declarative Host Ingress Proxy `/opt/caddy` files managed by `sandbox.caddy_store` and `modal-sandbox infra caddy backup|restore` (keeping `CADDY_STORE_PROFILE` in `.env` for profile selection).
     - `scratchpad/`: Persistent Markdown **Scratchpad Notes** (`<slug>.md`).
   - Perform a clean codebase cutover with no runtime fallback to legacy `env-store` or `caddy-store` repository names, while excluding `config` alongside `env-store` and `caddy-store` from `EXCLUDED_INFRA_REPOS` in the dashboard repository picker.

2. **Dashboard Scratchpad Tab with Free OpenCode AI Refinement (`sandboxes/sandbox/scratchpad/`)**:
   - Add a fourth `Scratchpad` tab (`#scratchpad`) to the **Sandbox Web Dashboard** and mount REST routes under `/api/scratchpad/*` inside Basic-authenticated `web_router`.
   - Install the OpenCode CLI (`opencode`) in the **Hosted Sandbox Control Plane** image (`sandboxes/sandbox/function.py`) and invoke `opencode run --format json` across free Zen models (`opencode/mimo-v2.6-flash-free`, `opencode/deepseek-v4.1-flash-free`, `opencode/big-pickle`, `opencode/nemotron-3.5-lightning-free`) in an isolated temporary `HOME` without requiring paid keys or credits.
   - Submitting raw text returns an AI-suggested title and improved Markdown in an editable review modal showing the exact target path `scratchpad/<slug>.md` (lowercase kebab-case with automatic `-2`, `-3` collision disambiguation).
   - **Accept & Commit** writes `# <Title>` + Markdown body to `github.com/${GH_ORG_NAME}/config/scratchpad/<slug>.md`; **Save Raw** commits the raw draft directly; **Reject** closes the modal without committing and preserves the raw composer draft.
   - Operators can browse and inspect saved notes from `config/scratchpad/` and click **Use in Builder** to prefill the Builder prompt.

## Consequences

- Operators manage one private repository (`github.com/${GH_ORG_NAME}/config`) for secrets, Caddy ingress backups, and Scratchpad Markdown notes.
- Existing `env-store` and `caddy-store` repositories on GitHub become historical archives superseded by `config`.
- The control plane image includes the OpenCode binary (~100 MB) and CA certificates so keyless free-model refinement works out of the box on Modal.
