# Shallow Repository Clone Depth in Sandboxes

Development and preview sandboxes launched via `sandbox/main.py` previously performed full Git repository clones, fetching the entire commit history of the target branch. For repositories with extensive commit histories, this incurred unnecessary network overhead, increased storage consumption, and slowed sandbox startup latency. We decided to enforce a fixed shallow clone depth of 50 commits (`--depth 50`) in `shared/startup.sh`. This ensures rapid container bootstrap while preserving enough recent commit history (up to 50 commits) for inspection, local branching, and development.

## Considered Options

- **Full clone default with opt-in shallow clone**: Retaining full commit history by default and requiring a CLI flag to shallow clone. Rejected because fast startup latency should be the default experience for all interactive and development sandboxes; full clone history is rarely needed during sandbox sessions.
- **Configurable `--git-depth` CLI flag in `sandbox/cli.py`**: Introducing a `--git-depth` flag to allow custom depth values or `--git-depth 0` for full clones. Rejected to avoid CLI option bloat and keep the runner interface simple; 50 commits is a pragmatic, generous constant for development sandboxes.
- **Applying `--depth 50` across all sandbox execution environments (including Factory Assembly Line)**: Enforcing `--depth 50` in `shared/factory_entrypoint.sh`. Rejected because automated assembly line agents (Planner and Coder) and verification tools may need complete branch history and merge bases against mainline to generate plans, inspect previous ticket commits, and compute accurate diffs across long-running feature branches.

## Consequences

- In `shared/startup.sh`, the Git clone invocation includes `--depth 50` alongside `--quiet`, `--branch "$BRANCH"`, and `--single-branch`.
- Sandboxes initialize substantially faster, transferring only the last 50 commits (or all commits if the repository has fewer than 50).
- Automated tests in `tests/test_sandbox/` verify that `shared/startup.sh` enforces the `--depth 50` parameter during repository cloning.
- The Git repository inside `/root/<repo-name>` is marked as a shallow clone (`.git/shallow`). If a developer inside an active sandbox requires older commits, they can fetch additional depth or unshallow using Git tooling.
