# Automatic SSH Config Registration for Modal Sandboxes

**Status**: Accepted (Amends [ADR 0006](0006-externalize-ssh-private-key-and-decouple-runners.md) and [ADR 0079](0079-hosted-sandbox-control-plane-function.md))

## Context

In [ADR 0006](0006-externalize-ssh-private-key-and-decouple-runners.md), SSH private key management was externalized to `~/.ssh/modal-sandbox` on the developer workstation while the public key was embedded into sandbox containers from `shared/ssh-key.pub`. When sandboxes launched, SSH connection instructions were printed in the terminal along with a VS Code / SSH config snippet.

However, developers had to manually copy and paste the snippet into `~/.ssh/config` every time a new sandbox was launched or recreated with new port assignments. Without manual pasting, connecting via `ssh <instance_name>` or opening VS Code Remote SSH sessions required repetitive manual edits.

## Considered Options

- **Manual Snippet Copy-Paste (Status Quo)**: Only print the configuration snippet to stdout. Rejected because it introduces unnecessary friction and human intervention into every sandbox development loop.
- **Idempotent Marker-Based Block Replacement**: Parse `~/.ssh/config` with custom start/end markers (`# BEGIN MODAL SANDBOX: <name>`) and replace matching blocks. Rejected because simple append is lower complexity, preserves existing developer configurations safely, and avoids brittle parser edge cases across varied user config styles.
- **Client-Side Automatic Appending with Opt-Out Flag (`--no-ssh-config`)**: Automatically append the formatted connection block to `~/.ssh/config` from the local CLI runner (`sandbox/main.py`), with `--no-ssh-config` available to bypass updates in headless or automated environments. Accepted because it delivers zero-click developer convenience locally while leaving cloud execution functions decoupled and side-effect free.

## Decisions

1. **Automatic SSH Configuration Registration**:
   - `sandbox/main.py` automatically appends SSH connection details to `~/.ssh/config` whenever a sandbox with SSH is provisioned (in both local execution and `--remote` mode).
   - Format matches the terminal output snippet:
     ```ssh-config
     Host <instance_name>
       HostName <ssh_host>
       Port <ssh_port>
       User root
       IdentityFile ~/.ssh/modal-sandbox
       StrictHostKeyChecking no
       UserKnownHostsFile /dev/null
     ```
   - Includes `UserKnownHostsFile /dev/null` alongside `StrictHostKeyChecking no` to eliminate host key collision warnings when Modal reuses host IP addresses.
2. **Opt-Out Control (`--no-ssh-config`)**:
   - Adds `--no-ssh-config` to `sandbox/cli.py` to allow skipping `~/.ssh/config` updates in automated or headless CI/CD environments.
3. **Graceful Fault Tolerance**:
   - If writing to `~/.ssh/config` fails (e.g. read-only filesystem or restricted permissions), `sandbox/main.py` logs a friendly warning to `sys.stderr` and continues execution without aborting the sandbox launch.
4. **Cloud Control Plane Isolation**:
   - The hosted cloud function (`sandbox/function.py`) remains pure and does not manipulate local container SSH configs; updates remain strictly a client CLI capability.

## Consequences

- Developers can immediately run `ssh <instance_name>` or attach VS Code Remote SSH without manual configuration copying.
- The `--no-ssh-config` flag allows non-interactive scripts to disable local filesystem writes.
- All source files remain strictly under the universal 500 physical line budget.
