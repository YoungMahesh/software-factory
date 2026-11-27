# Filesystem Snapshots and Persistence

The factory captures sandbox root filesystem state as a Modal Image and can launch another sandbox from that image. This preserves files and installed packages, while startup restarts services; it does not resume running processes. See the [Modal snapshot guide](https://modal.com/docs/guide/sandbox-snapshots) for platform behavior.

A Filesystem Snapshot covers the entire sandbox root filesystem, including all Builder Workspaces hosted there. Builder Workspace tracking records live separately in `factory-state-v1`, and mounted persistent volumes have their own lifecycles. Starting a new sandbox from a snapshot restores the captured files, not the source sandbox's Builder Workspace identities or mounted volume data.

## Capture

```bash
modal-sandbox --snapshot <sandbox-id> --snapshot-ttl 30 --snapshot-timeout 180

# Terminate the source only after capture succeeds.
modal-sandbox --snapshot <sandbox-id> --terminate
```

The factory default retention is 30 days, and capture timeout is 180 seconds. Both values must be positive. `--snapshot-ttl`, `--snapshot-timeout`, and `--terminate` are capture-only options; do not combine capture with launch flags such as `--repo`, `--name`, or `--vm`.

The snapshot module records metadata in the named Modal Dict `sandbox-snapshots`, with a local fallback at `~/.modal/sandbox-snapshots.json`. The hosted dashboard can list records, resume images, and delete registry records. Deleting a registry record does not delete the underlying image or its retained data.

## Resume

```bash
modal-sandbox --from-snapshot <image-id> --name resumed-box

# Reuse VM capabilities and T3 services when appropriate for the saved image.
modal-sandbox --from-snapshot <image-id> --name resumed-box --vm --t3
```

Use `--name` for a standalone restore or `--repo` for a repository launch, never both. The image must already contain the tools required by the selected flags; restoring does not rebuild it with new tooling layers.

Startup resolves the saved workspace markers and preserves the existing virtualenv. It skips repository cloning and package installation. Updating `requirements.txt` in the factory therefore affects fresh launches, while a resumed sandbox needs a manual install to acquire new dependencies:

```bash
# Run inside the restored Software Factory checkout and its virtualenv.
python -m pip install -r requirements.txt
```

Select service flags needed by the restored workspace and review the resulting connection details. Each new sandbox has a new generated instance name and connection alias.

## Persistent volumes

| Data | Storage |
| :--- | :--- |
| T3 history, provider transcripts, and usage caches | `t3code-usage-v1` mounted at `/root/.t3-storage`; startup hydrates supported local files and runs a synchronization daemon |
| Codex saved authentication | Assigned Codex Credential Profile volume mounted at `/root/.codex-profile`, configured independently from T3 history |
| Gradle cache and wrapper | `gradle-caches` at `/root/.gradle/caches` and `gradle-wrapper` at `/root/.gradle/wrapper` with `--react-native` |

T3 persistence is enabled with `--t3` by default. Set `--t3-usage-volume <name>` to choose the history volume, or `--no-t3-persist` to disable history synchronization. This volume is not a backup of arbitrary repository files or worktrees. Preserve source changes in Git or a filesystem snapshot. Codex Credential Profile assignment has its own configuration; see [AI tooling](../guides/ai-tooling.md).

## Credential handling

Snapshots can retain `.env`, `.git/env-vault/`, shell exports, provider authentication files, and other credentials written to the root filesystem. Capture performs no credential sanitization. Treat snapshot access as sensitive and review [the credential lifecycle](secrets.md) before sharing images. Persistent volumes also retain their data after a sandbox terminates.

Related decisions: [ADR 0024](../adr/0024-filesystem-snapshots-in-unified-sandbox-runner.md), [ADR 0048](../adr/0048-antigravity-acp-credential-preservation-in-filesystem-snapshots.md), [ADR 0069](../adr/0069-snapshot-workspace-target-persistence-and-venv-preservation.md), and [ADR 0071](../adr/0071-consolidate-filesystem-snapshot-lifecycle.md).
