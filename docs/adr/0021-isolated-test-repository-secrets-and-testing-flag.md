# Isolated Test Repository Secrets and Testing Flag

**Status**: superseded by ADR-0023

To prevent accidental modifications, data leaks, or confusing state overlap between active production projects and test targets, we decided to store all test repository credentials in an isolated top-level directory (`secrets_testing/<project-name>/`), add a dedicated `--testing` CLI flag across sandbox and factory launchers, and prefix ephemeral test Modal applications with `test-`.

## Considered Options

- **Co-located Subdirectories (`secrets/for-testing/<project-name>/`)**: Storing test credentials under a subfolder of `secrets/`. Rejected because it complicates secret discovery logic, mixes sensitive production secrets with throwaway test fixtures in the same directory tree, and risks accidental staging in production workflows.
- **Mocked / Dummy In-Memory Repositories**: Only testing pipelines against local synthetic git fixtures. Rejected because real GitHub clone authentication, network conditions, token scopes, and actual repository layout variations (such as legacy `GLOSSARY.md` versus `CONTEXT.md`) cannot be validated without real repositories.
- **Dedicated Top-Level Directory (`secrets_testing/`) with `--testing` Flag**: Accepted because it creates an unmistakable filesystem separation between operational target repositories (`secrets/`) and test fixtures (`secrets_testing/`), enables explicit CLI intent (`--testing` / `--test`), and keeps production directory trees clean.

## Consequences

- Test repository secrets are tracked under `secrets_testing/<project-name>/` (including `fetch.env`, `env.map`, and `.env` files).
- CLI runners (`sandbox/main.py` and factory dispatchers) support `--testing` (alias `--test`), resolving secret bundles from `secrets_testing/` and prefixing Modal apps with `test-` (e.g. `test-<project>-<random_id>`).
- Test repositories with legacy conventions (such as `GLOSSARY.md`) are explicitly supported by the Pre-flight Guard alongside `CONTEXT.md`.
