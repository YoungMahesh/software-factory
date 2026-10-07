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

**Antigravity Remote Control**:
A background reverse tunnel connection between the sandbox's Antigravity CLI and Google's Antigravity platform (https://antigravity.google.com), authenticated via the Antigravity OAuth Token, permitting remote monitoring, actuation, and interaction from a web browser without inbound open ports or Modal tunnel URLs.
_Avoid_: Antigravity web, agy proxy, remote tunnel

**React Native Tooling**:
A pre-baked Android development toolchain within the sandbox image including OpenJDK 17, Android SDK platforms, build-tools, NDK, and CMake.
_Avoid_: Android environment, mobile dependencies, Android emulator

**Metro Tunnel**:
A secure HTTPS tunnel forwarding traffic directly to the React Native or Expo Metro bundler development server running inside the sandbox.
_Avoid_: Metro proxy, bundler forward, mobile tunnel

**Modal Development Tooling**:
A runtime development environment within the sandbox combining a pre-baked Python 3 runtime, an automated virtual environment (`.venv`) pre-installed with the Modal SDK and project dependencies, and opt-in decrypted Modal Client Credentials (`~/.modal.toml`) for developing and running Modal workloads from within the sandbox.
_Avoid_: Python tooling, python runner, modal env

**Shared Workspace Secret**:
The centralized Modal secret collection (`share0`) mounted into all sandboxes unconditionally, providing shared organizational secrets—specifically `AGE_PRIVATE_KEY` for SOPS bootstrap—used to decrypt the Repository Fetch Secret, Cloudflare Tunnel token, and opt-in agent/tooling credentials.
_Avoid_: Global secret, root secret, default secret

**Repository Fetch Secret**:
A SOPS-encrypted environment file stored in version control at `secrets/<secret-name>/fetch.env`, staged into the sandbox image under `/root/secrets/repo/` and decrypted ephemerally into memory at container boot in `startup.sh` using `AGE_PRIVATE_KEY` to supply repository clone credentials (`GH_REPO`, `GH_TOKEN`, and optional `DOTENV_PRIVATE_KEY`), immediately scrubbed from disk before interactive shells or servers initialize.
_Avoid_: Repo secret, secret collection, fetch config, local secret

**Repository Environment Secrets**:
SOPS-encrypted environment files stored alongside `fetch.env` under `secrets/<secret-name>/` and mapped to destination file paths in the cloned repository via `secrets/<secret-name>/env.map`, decrypted ephemerally into the repository during container boot in `startup.sh` before staging files and `AGE_PRIVATE_KEY` are scrubbed.
_Avoid_: Dotenv secrets, repo envs, app secrets, env mappings

**Repository Env Mapping**:
The configuration file (`secrets/<secret-name>/env.map`) that defines explicit key-value associations between local encrypted secret files and their repository-relative destination file paths.
_Avoid_: Location file, env config, secret locations

**SOPS Decryption**:
A bootstrap mechanism during sandbox initialization that extracts `AGE_PRIVATE_KEY` from the Shared Workspace Secret (`share0`) to decrypt the Repository Fetch Secret (`secrets/<secret-name>/fetch.env`) and Cloudflare Tunnel token (`secrets/cloudflare.env`) in `startup.sh`, temporarily configures an Age key file at `~/.config/sops/age/keys.txt` (mode 0600) to execute the Tooling Setup Script (`/root/scripts/setup.sh` with `--agy`, `--modal`, and/or `--opencode`), and unconditionally purges `~/.config/sops` and unsets `AGE_PRIVATE_KEY` from memory to prevent credential persistence in active sandboxes.
_Avoid_: Sops setup, age injection, secret script

**Tooling Setup Script**:
A portable script (`scripts/setup.sh`) staged into the sandbox at `/root/scripts/setup.sh` that decrypts opt-in tooling credentials (`--modal`, `--agy`, `--opencode`) from the secrets directory into user configuration directories, running identically on host workstations and inside sandboxes.
_Avoid_: Repo setup script, secret decrypter, install script

**Modal Sandbox SSH Key**:
The dedicated SSH key pair used to authenticate into running sandboxes. The public key is tracked in version control at `shared/ssh-key.pub` and injected into the container's `/root/.ssh/authorized_keys`, while the private key is maintained out-of-band by developers at `~/.ssh/modal-sandbox` (mode 0600) and never tracked, stored, or decrypted in repository secrets or sandbox environments.
_Avoid_: Default SSH key, id_ed25519, root SSH key

**Antigravity OAuth Token**:
The authenticated session credential for the Antigravity CLI, encrypted with SOPS at `secrets/antigravity-oauth-token.json` and decrypted inside the sandbox (or locally) to `~/.gemini/antigravity-cli/antigravity-oauth-token` (mode 0600) via `scripts/setup.sh --agy`.
_Avoid_: Gemini token, antigravity auth token, cli token

**Shared Agent Configuration**:
Common editor and AI agent configuration files tracked in the repository root `shared/` directory (`shared/opencode.json`, `shared/antigravity-settings.json`, `shared/antigravity-keybindings.json`) and mounted into sandboxes at runtime.
_Avoid_: Sandbox config, local config, runner settings

**Modal Client Credentials**:
The authenticated client configuration and API token (`~/.modal.toml`) used by the Modal CLI and SDK to manage cloud resources. Decrypted with SOPS from `secrets/modal.toml` via `scripts/setup.sh --modal` (mode 0600), withheld from automated sandbox initialization by default to enforce credential isolation, and provisioned into sandboxes strictly when `--modal` is explicitly passed.
_Avoid_: Modal token, modal config, modal credentials

**OpenCode Credentials**:
A set of API keys and remote service tokens (`OPENCODE_GO_API_KEY`, `EXA_API_KEY`, `CONTEXT7_API_KEY`) encrypted with SOPS at `secrets/opencode.env` and decrypted inside the sandbox to `~/.config/opencode/opencode.env` (mode 0600) via `scripts/setup.sh --opencode`.
_Avoid_: OpenCode tokens, opencode keys, mcp secrets

**Shared Base Image**:
A cached Modal image definition built on Ubuntu 24.04 providing the foundational filesystem for both Standard Sandboxes and VM Sandboxes, pre-baked with common tooling including SSH server, SOPS, age, Git, ripgrep, Docker CLI binaries, Node.js 24, and pnpm.
_Avoid_: Base container, root image, runner image

**Browser Tooling**:
A pre-baked, headless Google Chrome instance installed by the `--browser` flag and shared by the Playwright and Chrome DevTools MCP servers, launched with the sandbox-free flags required when running as root.
_Avoid_: Browser MCP, headless browser setup, chrome layer

**Cloudflare Tunnel**:
A background ingress service (`cloudflared`) pre-baked into the Shared Base Image and installed as a service by default in the sandbox, authenticated via `CF_TOKEN` decrypted at boot from `secrets/cloudflare.env` using SOPS, securely routing external traffic from `https://3000.mahesh0.dev` directly to local port 3000 without requiring open inbound firewall ports.
_Avoid_: Cloudflare proxy, cloudflare daemon, cf tunnel, modal web tunnel, web url tunnel
