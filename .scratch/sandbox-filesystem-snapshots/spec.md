# Spec: Filesystem Snapshots in Unified Sandbox Runner

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

When working with cloud sandboxes in the software factory, bootstrapping an environment from scratch (cloning target repositories, installing large dependency trees via package managers like `pnpm` or `npm`, and building toolchains) incurs noticeable startup latency on every session. Furthermore, when a developer or agent configures a complex interactive workspace, experiments with modifications, or needs to freeze a debugging state, there is no mechanism to capture the running container's filesystem and restore it later.

Currently, the unified sandbox runner strictly builds fresh images from scratch on every run and requires version-controlled repository secrets or organization tokens. Developers cannot snapshot a live sandbox session to create a checkpoint, nor can they launch sandboxes from existing filesystem snapshots without re-cloning repositories and re-installing dependencies.

## Solution

Extend the unified sandbox runner and startup orchestration to support Modal Filesystem Snapshots:

1. **Snapshot Capture Capability**: Add a dedicated CLI execution mode to capture the root filesystem of an active sandbox into a reusable snapshot image using Modal's `snapshot_filesystem()` API.
2. **Filesystem Buffer Flushing**: Automatically execute a disk sync inside the sandbox prior to snapshotting to ensure unwritten file buffers are committed.
3. **Retention Management**: Allow configuring a custom Time-To-Live (TTL) in integer days, defaulting to 30 days in alignment with Modal's lifecycle defaults.
4. **Non-Destructive by Default with Optional Termination**: Keep the target sandbox running after snapshot capture by default, with an opt-in flag to terminate the container immediately upon snapshot completion.
5. **Snapshot Restoration Capability**: Allow launching fresh Standard Sandboxes or VM Sandboxes directly from a snapshot image ID, bypassing image compilation layers.
6. **Optional Secrets with Mandatory Naming**: Make repository secrets optional when launching from a snapshot image. If secrets are omitted, require an explicit application name for tracking.
7. **Fast In-Sandbox Resume**: Pass a snapshot resume signal to the startup script to bypass repository cloning and dependency installations while preserving SSH configuration and requested background tooling daemons (OpenCode, Antigravity, Cloudflare).
8. **Runtime Parity**: Support filesystem snapshots across both Standard Sandboxes and VM Sandboxes with explicit user notices regarding ephemeral volumes and Docker daemon storage.

## User Stories

1. As a developer debugging a complex repository state in a running sandbox, I want to capture a point-in-time filesystem snapshot using my sandbox ID, so that I have a durable checkpoint of my modified files.
2. As a developer taking a snapshot of a running sandbox, I want in-flight disk buffers to be flushed with `sync` before the snapshot is calculated, so that my snapshotted files are consistent and not corrupted.
3. As a developer capturing a snapshot, I want the CLI to output the generated Image ID and an exact copy-pasteable resume command, so that I can immediately spin up a clone of that environment.
4. As a developer managing temporary test environments, I want to specify an expiration TTL in days, so that unused test snapshots are automatically garbage-collected after my specified retention period.
5. As a developer creating long-term template environments, I want the snapshot to default to 30 days if I don't provide a TTL flag, so that it follows Modal's standard retention convention.
6. As a developer capturing an intermediate checkpoint while continuing to work, I want snapshotting to be non-destructive by default, so that my active SSH session or development server is not terminated.
7. As a developer finishing a work session, I want an optional flag to terminate the sandbox immediately after the snapshot completes, so that I don't incur unnecessary cloud compute costs.
8. As a developer spinning up a workspace from a previously saved snapshot, I want to supply the snapshot Image ID to the unified runner, so that my sandbox boots in seconds without re-cloning the repository.
9. As a developer launching from a snapshot image without repository secrets, I want the CLI to require an application name, so that the Modal App and terminal status have a clear, recognizable identity.
10. As a developer launching from a snapshot with fresh repository secrets, I want the runner to apply new decrypted environment secrets into the workspace, so that I can update keys while keeping installed dependencies.
11. As a developer launching from a snapshot, I want the startup script to detect the resumed state and skip `git clone` and `pnpm install`, so that cold-start latency is minimized.
12. As a developer connecting to a resumed sandbox, I want my SSH key to be injected and background services (OpenCode, Antigravity, Cloudflare) to start normally, so that I have immediate remote access.
13. As a developer using VM Sandboxes with Docker, I want to snapshot my VM sandbox root filesystem, so that I can checkpoint my VM workspace.
14. As a developer snapshotting a VM sandbox, I want to see a clear notice that mounted volumes and Docker daemon layers are not stored in root filesystem snapshots, so that I understand storage boundaries.
15. As a developer accidentally passing conflicting flags (like capturing a snapshot and launching from a snapshot simultaneously), I want immediate validation errors, so that I do not produce undefined sandbox states.

## Implementation Decisions

- **Unified CLI Interface**:
  - Add `--snapshot <sandbox-id>` for snapshot capture.
  - Add `--snapshot-ttl <days>` (integer days, default: 30) for retention.
  - Add `--terminate` to shut down the container after capture.
  - Add `--from-snapshot <image-id>` to boot from a snapshot image.
  - Add `--name <app-name>` for explicit sandbox naming (mandatory when `--from-snapshot` is used without `--secret`).
  - Enforce mutual exclusion between `--snapshot` and launch-specific arguments.

- **Snapshot Capture Lifecycle**:
  - Attach to running sandbox via Modal Sandbox lookup.
  - Run `sync` command inside sandbox process execution prior to snapshotting.
  - Execute filesystem snapshot with calculated wire TTL (`days * 86400`).
  - Print structured access details including Image ID and resumption command.
  - Conditionally invoke sandbox termination if requested.

- **Snapshot Restoration Lifecycle**:
  - Use Modal Image lookup by ID as the container base image.
  - If secrets are provided, stage local secret files onto image; if omitted, use image directly.
  - Inject `RESUME_SNAPSHOT=1` into container environment variables.
  - Derive application name from `--name` when secrets are absent.

- **Startup Entrypoint Orchestration**:
  - In the startup entrypoint script, evaluate `RESUME_SNAPSHOT`.
  - When enabled, skip secret decryption staging checks and git clone execution.
  - Dynamically discover existing repository working directory under `/root/` to set target directory.
  - Skip package manager installations (`pnpm install`, `npm install`, `pip install`).
  - Execute SSH daemon setup, authorized keys injection, and requested tooling daemons.

- **Runtime & Volume Caveats**:
  - Support both Standard Sandboxes and VM Sandboxes.
  - Output explicit notice regarding mounted volumes and Docker daemon persistence boundaries when snapshotting VM sandboxes.

## Testing Decisions

- **What makes a good test**:
  - Tests should verify externally observable CLI contract behavior: argument parsing, validation errors, mutual exclusion rules, output formatting, environment variable injection, and startup script resume branching, without mocking internal timing loops.

- **Primary Seams**:
  - CLI Argument Parsing & Validation Seam: Unit tests verifying `--snapshot`, `--snapshot-ttl`, `--terminate`, `--from-snapshot`, and `--name` validation rules, mutual exclusion, and error handling.
  - Runner Execution & Output Seam: Tests verifying that snapshot capture invokes `sync`, requests snapshot with correct TTL seconds, formats console output, and respects `--terminate`. Tests verifying that snapshot restore injects `RESUME_SNAPSHOT=1` and configures the base image correctly.
  - Startup Script Resume Seam: Verification tests ensuring that `startup.sh` cleanly bypasses `git clone` and package installation when `RESUME_SNAPSHOT=1` is set and an existing repo directory is found.

- **Prior art**:
  - `tests/test_sandbox.py`: Existing subprocess CLI validation, argument parser tests, and startup script structure assertions.

## Out of Scope

- Memory Snapshots (Modal's experimental RAM state snapshotting is out of scope; only root filesystem snapshots are supported).
- Directory Snapshots (capturing isolated subdirectories for mounting into separate containers is out of scope).
- Automated cron snapshot scheduling.
- Web UI snapshot management in Factory Studio (this spec focuses on the unified sandbox runner CLI).

## Further Notes

- Implements Architectural Decision Record ADR 0045 (`docs/adr/0045-filesystem-snapshots-in-unified-sandbox-runner.md`).
- Aligns with canonical domain glossary definitions in `CONTEXT.md` ("Filesystem Snapshot", "Standard Sandbox", "VM Sandbox").
