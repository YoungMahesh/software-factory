# Remove Working Directory Mutation From Sandbox Bashrc

Previously, `shared/startup.sh` appended `cd $TARGET_DIR` to `~/.bashrc` during sandbox initialization. This was intended to automatically place interactive shell users inside the cloned repository or standalone workspace upon login. However, because `.bashrc` is evaluated on interactive bash subshells and remote developer environments (such as VS Code Remote - SSH or agent subshells), injecting `cd <path>` into `.bashrc` hijacked the working directory of every subshell, broke IDE terminal directory restoration, and prevented developers and tooling from executing in `/root` or parent paths without being forced back to the workspace root. We decided to unconditionally remove `cd $TARGET_DIR` from `~/.bashrc` across all sandbox launches, leaving the default working directory as `/root` and preserving shell working directory integrity for interactive terminals and remote IDEs.

## Considered Options

- **Keep `cd $TARGET_DIR` in `.bashrc` by default**: Continue automatically changing directory on shell startup. Rejected because it violates shell conventions, hijacks subshell working directories, disrupts remote SSH IDE workspace state, and interferes with commands executed in other directories.
- **Make working directory navigation opt-in via a CLI flag (e.g. `--cd-repo`)**: Add a flag to `sandbox/cli.py` to optionally append `cd $TARGET_DIR` to `.bashrc`. Rejected because mutating `.bashrc` with `cd` is fundamentally an anti-pattern for interactive subshells; developers can simply `cd <path>` or configure editor workspace settings.
- **Export a helper environment variable or shortcut alias (`WORKSPACE` / `repo`)**: Inject an alias or environment variable into `.bashrc` pointing to `$TARGET_DIR`. Rejected because keeping the shell profile clean and unpolluted is preferable to adding bespoke aliases.
- **Unconditionally remove `cd $TARGET_DIR` from `~/.bashrc`**: Remove the line from `shared/startup.sh` across all sandbox launches without adding replacement aliases or environment variables. Accepted because it cleanly restores standard shell directory semantics, fixes remote SSH IDE toolchains, eliminates subshell directory hijacking, and avoids shell profile pollution.

## Consequences

- `shared/startup.sh` no longer appends `cd $TARGET_DIR` to `~/.bashrc`.
- Interactive SSH and terminal sessions open in `/root`, allowing developers, remote IDEs, and tools to manage their working directories predictably without forced redirection.
- In-container background daemons (`t3 serve`, `opencode serve`) and container build/setup steps in `startup.sh` remain unaffected as they explicitly target or pass `$TARGET_DIR`.
- Unit tests in `tests/test_sandbox/test_cli_args.py` verify that `startup.sh` does not write working directory changes to `~/.bashrc`.
