# Modal Sandboxes

Isolated cloud development and execution environments running on Modal with agent and development tooling.

## Language

**VM Sandbox**:
A Modal sandbox execution environment configured with full virtual machine virtualization, custom kernel privileges, Docker daemon support, and swapfile allocation.
_Avoid_: Container sandbox, VM instance, Docker runner

**Standard Sandbox**:
A lightweight container sandbox on Modal running directly on the container runtime without virtualized hardware abstraction or Docker daemon capabilities.
_Avoid_: Basic sandbox, container VM

**OpenCode Server**:
A background web and agent server bound to a dedicated encrypted tunnel port, protected by a per-launch generated access password.
_Avoid_: OpenCode IDE, code server

**Antigravity CLI**:
Google's terminal agent interface installed in the sandbox user environment with pre-mounted configuration and credentials.
_Avoid_: Gemini CLI, antigravity-ide
