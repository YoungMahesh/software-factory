# Filesystem Snapshots in Unified Sandbox Runner

We added Filesystem Snapshot capture and restoration capabilities to `sandbox/main.py` using Modal's `snapshot_filesystem()` API. Developers can freeze an active sandbox session into a reusable `modal.Image` and launch fresh Standard or VM Sandboxes from snapshot images, bypassing git cloning and dependency installation for near-instant cold starts.

## Considered Options

- **Subcommands (`launch` and `snapshot`)**: Refactoring `sandbox/main.py` into distinct subcommands. Rejected to maintain strict backward compatibility with existing CLI invocations and CI scripts.
- **Separate script (`sandbox/snapshot.py`)**: Placing snapshot capture in a standalone utility. Rejected to preserve ADR 0016's principle of a unified sandbox runner managing sandbox lifecycles in one entrypoint.
- **Mandatory secrets on restore**: Requiring `--secret` even when booting from a snapshot. Rejected because snapshots already contain the project workspace and dependencies; allowing offline resumption via mandatory `--name` enables rapid cold starts.

## Consequences

- `sandbox/main.py` gains `--snapshot <sandbox-id>`, `--snapshot-ttl <days>`, `--terminate`, `--from-snapshot <image-id>`, and `--name <app-name>`.
- Snapshot capture runs `sync` inside the sandbox before snapshotting and displays the resulting Image ID and resume command.
- When launching from `--from-snapshot` without `--secret`, `--name` is required and `RESUME_SNAPSHOT=1` instructs `shared/startup.sh` to bypass git clone and dependency installation.
- Snapshot TTL defaults to 30 days per Modal's v1.5 standard.
