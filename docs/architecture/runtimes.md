# Execution Runtimes: Container vs. Linux VM

Modal Sandboxes supports two execution environments to balance startup speed with virtualization requirements.

## Runtime Comparison

| Dimension | Standard Container | Linux VM Sandbox (`--vm`) |
| :--- | :--- | :--- |
| **Modal Runtime** | Standard (`runtime=None`) | Stable VM (`runtime="vm"`) |
| **CLI Flag** | Default | `--vm` |
| **Startup Latency** | ~2–5 seconds | ~10–15 seconds |
| **Docker-in-Docker** | No (restricted permissions) | **Yes** (dockerd pre-configured) |
| **Kernel Privileges** | Restricted container namespace | Full Linux kernel privileges |
| **RAM Configuration** | Burstable `(128, 16384)` MiB | Burstable `(128, 16384)` MiB |
| **Swapfile Support** | Disabled | Automatically allocated |
| **Best For** | Python apps, web APIs, scripts, AI agents | Docker compose, integration tests, custom daemons |

---

## 1. Standard Container Sandbox

Standard sandboxes run on Modal's lightweight container runtime. They offer sub-second to low-second cold start times and are ideal for the majority of developer workflows, including:

- Running Python, TypeScript, and Go development tools.
- Hosting web development servers (Next.js, FastAPI, Vite).
- Interacting with AI coding agents (T3 Code, OpenCode, Pi).
- Inspecting code with remote SSH shells.

```bash
# Provision a standard container sandbox
modal-sandbox --name dev-box
```

---

## 2. Linux VM Sandbox (`--vm`)

When `--vm` is specified, the launcher instructs Modal to boot a virtual machine with full kernel isolation (see [ADR 0067](../adr/0067-migrate-vm-runtime-to-modal-stable-runtime.md)).

Key capabilities include:
- **Docker Daemon**: The VM boots with an active Docker daemon. You can run `docker build`, `docker run`, and `docker compose up` directly inside the sandbox.
- **Custom System Daemons**: Run background services, database daemons, and system services that require `systemd` or root privileges.
- **Swap Allocation**: Swapfile memory allocation is managed automatically to handle intensive build tasks.

```bash
# Provision a Linux VM sandbox with Docker support
modal-sandbox --name vm-box --vm
```

Inside the VM sandbox:

```bash
ssh vm-box "docker --version && docker run hello-world"
```
