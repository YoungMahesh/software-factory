# Opt-In Full Git Repository Clone in Sandboxes

ADR 0066 established a default shallow clone depth of 50 commits (`--depth 50`) for development and preview sandboxes launched via `sandbox/main.py` to optimize startup latency and container bootstrap time. However, specific development, debugging, and migration workflows require complete commit histories, such as running repository-wide git bisect, inspecting commits beyond the recent 50 commits, or computing complete merge bases without requiring in-sandbox manual `git fetch --unshallow` steps. We decided to introduce an opt-in CLI flag, `--full-clone`, in `sandbox/main.py` (via `sandbox/cli.py`) that bypasses the shallow clone depth limit and downloads all commits of the target branch during initial container provisioning.

## Considered Options

- **Numeric `--git-depth [N]` argument**: Providing a configurable depth integer where `0` or omitting the parameter represents full clone. Rejected because users rarely need fine-grained control over shallow clone depths other than the fast default (50) or complete history, and a boolean flag offers a clearer, safer CLI interface without option bloat.
- **Cloning all remote branches and tags (`--no-single-branch`)**: Downloading all commits across all remote branches. Rejected because sandbox sessions target a specific branch (`--github-branch`); cloning all remote branches introduces significant overhead without development benefit. Retaining `--single-branch` while removing `--depth 50` delivers complete commit history for the desired branch.
- **Passing full-clone setting as a positional argument to `shared/startup.sh`**: Modifying the script invocation arguments (`bash /root/scripts/startup.sh <branch> <full_clone>`). Rejected to keep positional arguments consistent and avoid breaking invocation contracts. Passing the setting via container environment variable `FULL_CLONE="1"` conforms with all other optional sandbox tooling and runtime configurations.

## Consequences

- A `--full-clone` boolean flag is available on `sandbox/main.py`.
- In `sandbox/cli.py`, `validate_args()` enforces that `--full-clone` can only be used when fetching a repository (requires `-s/--secret`) and cannot be combined with `--snapshot` or `--from-snapshot`.
- When `--full-clone` is passed, `sandbox/main.py` sets `FULL_CLONE="1"` in the sandbox environment variables and lists "Full Git Clone" in the launch announcement banner.
- In `shared/startup.sh`, when `FULL_CLONE="1"`, the clone command omits `--depth 50` while retaining `--quiet --branch "$BRANCH" --single-branch`. When unset or `0`, the default `--depth 50` clone behavior is preserved.
- Automated tests in `tests/test_sandbox/test_cli_args.py` verify `--full-clone` argument parsing, validation rules, environment variable propagation, and startup script execution.
