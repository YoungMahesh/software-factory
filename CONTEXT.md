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

**React Native Tooling**:
A pre-baked Android development toolchain within the sandbox image including OpenJDK 17, Android SDK platforms, build-tools, NDK, and CMake.
_Avoid_: Android environment, mobile dependencies, Android emulator

**Metro Tunnel**:
A secure HTTPS tunnel forwarding traffic directly to the React Native or Expo Metro bundler development server running inside the sandbox.
_Avoid_: Metro proxy, bundler forward, mobile tunnel

**Python Tooling**:
A pre-baked Python 3 and pip runtime environment within the sandbox image configured with global package installation privileges and automatic dependency resolution.
_Avoid_: Python environment, pip runner, Python container

**SOPS Decryption**:
A bootstrap mechanism during sandbox initialization that extracts the `AGE_PRIVATE_KEY` from Modal Secrets, configures the Age key file at `~/.config/sops/age/keys.txt` (mode 0600), and executes repository decryption scripts (`secrets/setup.sh`).
_Avoid_: Sops setup, age injection, secret script

