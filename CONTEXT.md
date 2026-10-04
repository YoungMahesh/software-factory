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
A pre-baked Python 3 and venv runtime environment within the sandbox image configured to automatically provision an isolated virtual environment (`.venv`) in the cloned repository root, install dependencies from `requirements.txt`, and auto-activate in developer login sessions.
_Avoid_: Python environment, pip runner, Python container

**SOPS Decryption**:
A bootstrap mechanism during sandbox initialization that extracts the `AGE_PRIVATE_KEY` from Modal Secrets, configures the Age key file at `~/.config/sops/age/keys.txt` (mode 0600), and executes repository decryption scripts (`scripts/setup.sh`).
_Avoid_: Sops setup, age injection, secret script

**Modal Sandbox SSH Key**:
The dedicated SSH key pair used to authenticate into running sandboxes. The public key is tracked in version control at `shared/ssh-key.pub` and injected into the container's `/root/.ssh/authorized_keys`, while the private key is encrypted with SOPS at `secrets/ssh-private-key` and decrypted locally to `~/.ssh/modal-sandbox` (mode 0600).
_Avoid_: Default SSH key, id_ed25519, root SSH key

**Antigravity OAuth Token**:
The authenticated session credential for the Antigravity CLI, encrypted with SOPS at `secrets/antigravity-oauth-token.json` and decrypted inside the sandbox (or locally) to `~/.gemini/antigravity-cli/antigravity-oauth-token` (mode 0600) via `scripts/setup.sh`.
_Avoid_: Gemini token, antigravity auth token, cli token

**Shared Agent Configuration**:
Common editor and AI agent configuration files tracked in the repository root `shared/` directory (`shared/opencode.json`, `shared/antigravity-settings.json`, `shared/antigravity-keybindings.json`) and mounted into sandboxes at runtime.
_Avoid_: Sandbox config, local config, runner settings

**Modal Client Credentials**:
The authenticated client configuration and API token (`~/.modal.toml`) used by the Modal CLI and SDK on host workstations to manage cloud resources. Decrypted with SOPS from `secrets/modal.toml` only when explicitly requested via `scripts/setup.sh --modal` (mode 0600), and intentionally withheld from automated sandbox initialization to enforce credential isolation.
_Avoid_: Modal token, modal config, modal credentials



