# Modal Sandboxes

Isolated cloud development and execution environments running on Modal with developer and agent tooling.

## Language

**VM Sandbox**:
A Modal sandbox execution environment configured with full virtual machine virtualization (`runtime="vm"`), custom kernel privileges, Docker daemon support, burstable RAM `(128, 16384)` MiB identical to Standard Sandboxes, and swapfile allocation.
_Avoid_: Container sandbox, VM instance, Docker runner

**Standard Sandbox**:
A lightweight container sandbox on Modal running directly on the container runtime without virtualized hardware abstraction or Docker daemon capabilities.
_Avoid_: Basic sandbox, container VM

**Standalone Sandbox**:
A Modal sandbox execution environment provisioned without a Target Repository (`-r/--repo`), launched under a constant Modal App named via `--name` with an empty Git repository and default `.gitignore` initialized under `/root/<sandbox-name>`, and configured to run without cloning a remote target repository.
_Avoid_: Empty sandbox, blank runner, scratch container

**Standalone Quickstart**:
The minimal onboarding workflow that provisions an isolated cloud execution environment using only `modal-sandbox --name <name>` and standard Modal CLI authentication (`modal setup`), without requiring repository credentials, GitHub personal access tokens, or encryption keys.
_Avoid_: Zero-secret start, basic setup, blank init

**Modal Sandbox CLI**:
The primary command-line interface executable (`modal-sandbox`) packaged via `pyproject.toml` and registered from `sandbox.main:main`, enabling developers to provision, inspect, snapshot, and resume Modal execution environments directly from any terminal.
_Avoid_: Runner script, main.py, sandbox wrapper

**Named Sandbox Runner**:
A sandbox provisioning model in `sandbox/main.py` where the Modal App name remains constant (derived from the repository name or `--name`) while individual sandbox execution environments are uniquely named inside that App.
_Avoid_: Static runner, single-app runner, constant container

**Shallow Repository Clone**:
A Git checkout optimization in development sandboxes that truncates commit history on the target branch to a fixed maximum depth of 50 commits, accelerating container boot latency and saving network transfer while maintaining sufficient recent history for active development.
_Avoid_: Partial clone, shallow branch, depth clone, truncated repo

**Full Git Clone**:
An opt-in Git checkout configuration (`--full-clone`) in development sandboxes that downloads all commits of the target branch during container provisioning, bypassing the shallow clone depth limit for workflows requiring complete commit histories.
_Avoid_: Unshallow clone, complete fetch, deep repo

**Filesystem Snapshot**:
A point-in-time, copy-on-write capture of a Modal sandbox's root filesystem stored as a reusable `modal.Image` with an associated Time-To-Live (TTL), used to persist workspace state or accelerate subsequent sandbox cold starts without repeating repository cloning and dependency installation.
_Avoid_: Memory snapshot, container backup, sandbox image, VM snapshot

**OpenCode Server**:
A background web and agent server bound to a dedicated encrypted tunnel port, protected by a per-launch generated access password.
_Avoid_: OpenCode IDE, code server

**T3 Code Server**:
A background agent harness control surface running inside the sandbox (`t3 serve`), managing local CLI agents across isolated Git worktrees, bound to a dedicated encrypted tunnel port.
_Avoid_: T3 IDE, t3 daemon, Theo agent runner, t3 web

**Pairing URL**:
The public HTTPS URL emitted by T3 Code (`t3 pair` or sandbox launch metadata) containing the Modal application tunnel domain and a cryptographically generated pairing token (`https://<sandbox-tunnel>.modal.host/pair#token=...`), enabling external browser and desktop app pairing with the remote T3 Code Server.
_Avoid_: Local pairing URL, private IP link, direct socket URL

**Herdr Multiplexer**:
An agent-aware terminal multiplexer and background session runtime (https://herdr.dev) pre-baked into `/usr/local/bin` via `--herdr`, enabling persistent agent workflows, process status tracking across panes, and remote attachment over SSH.
_Avoid_: Terminal multiplexer, tmux clone, herdr daemon, herdr runner

**Pi Coding Agent CLI**:
A minimal, extensible terminal coding agent interface (https://pi.dev) installed into the sandbox user environment via `--pi`.
_Avoid_: Pi agent, pi terminal, pi runner

**Antigravity CLI**:
Google's terminal agent interface installed in the sandbox user environment with pre-mounted configuration and credentials.
_Avoid_: Gemini CLI, antigravity-ide

**Antigravity Remote Control**:
A background reverse tunnel connection between the sandbox's Antigravity CLI and Google's Antigravity platform (https://antigravity.google.com), authenticated via the Antigravity OAuth Token, permitting remote monitoring, actuation, and interaction from a web browser without inbound open ports or Modal tunnel URLs.
_Avoid_: Antigravity web, agy proxy, remote tunnel

**React Native Tooling**:
A pre-baked Android and React Native development toolchain within the sandbox image including OpenJDK 17, Android SDK platforms, build-tools, NDK, CMake, Watchman for file indexing, a tuned inotify file watch limit (524,288), and `@expo/ngrok` for tunnel connectivity.
_Avoid_: Android environment, mobile dependencies, Android emulator

**Metro Tunnel**:
A secure HTTPS tunnel forwarding traffic directly to the React Native or Expo Metro bundler development server running inside the sandbox.
_Avoid_: Metro proxy, bundler forward, mobile tunnel

**Modal Development Tooling**:
A runtime development environment within the sandbox combining a pre-baked Python 3 runtime, an automated virtual environment (`.venv`) pre-installed with the Modal SDK and project dependencies, and opt-in Modal Client Credentials (`MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` / `~/.modal.toml`) for developing and running Modal workloads from within the sandbox.
_Avoid_: Python tooling, python runner, modal env

**Factory Environment Configuration**:
The unified, uncommitted environment file (`.env`) at the workspace root (templated by `.env.example`) providing all control plane authentication, database credentials, single-organization GitHub access tokens, ingress tokens, and AI tooling credentials, injected into Modal sandboxes and control plane functions as native process environment variables.
_Avoid_: Config file, root env, secret bundle

**Shared Workspace Secret**:
An optional Modal secret collection (`share0`) or environment variable providing `AGE_PRIVATE_KEY` for SOPS bootstrap, strictly invoked when a cloned target repository provides an In-Repo Secret Manifest (`.secrets/env.map`).
_Avoid_: Global secret, root secret, default secret

**Test Organization Scope**:
The GitHub organization configured via `GH_ORG_NAME` in `.env`, within which `test-` prefixed repositories are targeted for automated pipeline verification and ephemeral integration testing without requiring a dedicated testing organization.
_Avoid_: Test org, mock org, testing workspace

**Test Repository Baseline**:
The designated minimal test fixture repository (`test-live-test1` under the configured `GH_ORG_NAME`) used across automated live integration scripts to validate sandbox creation, secret decryption, and workspace initialization.
_Avoid_: Default test repo, test mock, dummy repo

**Sandbox Live Verification**:
An automated, ephemeral integration test procedure that provisions a live Modal sandbox against the Test Repository Baseline (`test-live-test1`), asserts container bootstrap and git clone invariants, exercises modified runner capabilities, and guarantees immediate sandbox termination upon completion.
_Avoid_: Manual live test, smoke run, sandbox healthcheck

**SOPS Decryption**:
A bootstrap mechanism during sandbox initialization that uses `AGE_PRIVATE_KEY` to decrypt repository credentials when an In-Repo Secret Manifest (`env.map`) is present in the cloned target repository.
_Avoid_: Sops setup, age injection, secret script

**Tooling Setup Script**:
A portable script (`scripts/setup.sh`) staged into the sandbox at `/root/scripts/setup.sh` that provisions opt-in tooling credentials (`--modal`, `--agy`, `--opencode`) from environment variables into user configuration directories, running identically on host workstations and inside sandboxes.
_Avoid_: Repo setup script, secret decrypter, install script

**Modal Sandbox SSH Key**:
The dedicated SSH key pair used to authenticate into running sandboxes. The public key is tracked in version control at `shared/ssh-key.pub` (or overridden via `SSH_AUTHORIZED_KEY` in `.env`) and injected into the container's `/root/.ssh/authorized_keys`, while the private key is maintained out-of-band by developers at `~/.ssh/modal-sandbox` (mode 0600) and never tracked or committed.
_Avoid_: Default SSH key, id_ed25519, root SSH key

**Antigravity OAuth Token**:
The authenticated session credential for the Antigravity CLI and T3 Code provider instances, configured via the `ANTIGRAVITY_TOKENS` JSON profile array in `.env` and provisioned dynamically to `~/.gemini/antigravity-cli/profiles/` and `~/.t3/userdata/providers/antigravity/` by `scripts/setup.sh --agy`.
_Avoid_: Gemini token, antigravity auth token, cli token

**Shared Agent Configuration**:
Common editor and AI agent configuration files tracked in the repository root `shared/` directory (`shared/opencode.json`, `shared/antigravity-settings.json`, `shared/antigravity-keybindings.json`, `shared/antigravity-onboarding.json`, `shared/pi-settings.json`, `shared/pi-models.json`, `shared/t3-keybindings.json`) and mounted into sandboxes at runtime.
_Avoid_: Sandbox config, local config, runner settings

**Sandbox Shell Aliases**:
A curated collection of interactive shell shortcuts for Docker and Git operations tracked in `shared/aliases.bash`, staged into sandboxes at `/root/.bash_aliases`, and automatically sourced in `~/.bashrc` across all sandbox runtime modes.
_Avoid_: Terminal shortcuts, bash aliases script, developer helpers

**Sandbox Git Configuration**:
Declarative global Git configuration tracked in `shared/gitconfig`, staged into the Shared Base Image at `/root/.gitconfig`, providing default branch initialization (`main`) and GitHub credential helpers (`gh auth git-credential`). Host user authorship (`GIT_AUTHOR_*` and `GIT_COMMITTER_*`) is dynamically resolved by `SandboxLauncher` during container provisioning and injected into the container environment with generic fallback defaults (`Modal Sandbox User <sandbox@modal.local>`).
_Avoid_: Dynamic git config, inline git config, hardcoded git config

**Cloudflare Tunnel Domain**:
The public hostname routed by Cloudflare Tunnel to container port 3000, configured via `MODAL_SANDBOX_TUNNEL_DOMAIN` (or `CLOUDFLARE_TUNNEL_DOMAIN`), announced during sandbox readiness output or defaulting to a port readiness notice when unconfigured.
_Avoid_: Static tunnel URL, hardcoded tunnel domain

**Modal Client Credentials**:
The authenticated multi-account client credentials configured via `MODAL_TOKENS` in `.env` (a JSON array of profile objects) or written to `~/.modal.toml` via `scripts/setup.sh --modal` (mode 0600), allowing the Modal CLI and SDK to manage cloud resources across workspaces within the sandbox.
_Avoid_: Modal token, modal config, modal credentials

**OpenCode Credentials**:
API keys and service tokens (`OPENCODE_GO_API_KEY`) provided via `.env` and written inside the sandbox to `~/.config/opencode/opencode.env` (mode 0600) via `scripts/setup.sh --opencode`.
_Avoid_: OpenCode tokens, opencode keys, mcp secrets

**Shared Base Image**:
A cached Modal image definition built on Ubuntu 24.04 providing the foundational filesystem for both Standard Sandboxes and VM Sandboxes, pre-baked with common tooling including SSH server, SOPS, age, Git, ripgrep, tree, lsof, psmisc, fd, Python 3 (with venv and uv), Docker CLI binaries (including Buildx and Compose v2), Node.js 24, and pnpm.
_Avoid_: Base container, root image, runner image

**Browser Tooling**:
A pre-baked, headless Google Chrome instance installed by the `--browser` flag and shared by the Playwright and Chrome DevTools MCP servers, launched with the sandbox-free flags required when running as root.
_Avoid_: Browser MCP, headless browser setup, chrome layer

**Cloudflare Tunnel**:
A background ingress service (`cloudflared`) pre-baked into the Shared Base Image and installed as a service by default in the sandbox, authenticated via `CLOUDFLARE_TUNNEL_TOKEN` provided by the Factory Environment Configuration (`.env`), securely routing external traffic directly to local web ports without requiring open inbound firewall ports.
_Avoid_: Cloudflare proxy, cloudflare daemon, cf tunnel

**Universal File Line Budget**:
A repository-wide size constraint requiring every production source file and executable automated test file to contain no more than 500 physical lines (`wc -l`).
_Avoid_: File size limit, code line limit, test budget, 500-line rule

**Centralized Organization Credentials**:
The single-organization GitHub access configuration defined via `GH_TOKEN` and `GH_ORG_NAME` in the Factory Environment Configuration (`.env`), replacing legacy multi-file secret bundles (`secrets/github-orgs.env`).
_Avoid_: Org token file, github orgs secret, project fetch secret

**Central Environment Store**:
A dedicated private GitHub repository (`env-store` under `${GH_ORG_NAME}`) that securely houses SOPS-encrypted environment files and directory mappings organized by target repository name, serving as the centralized secret vault for public and private workspaces without polluting open-source codebases.
_Avoid_: Central secrets repo, github vault, secret bucket

**Host-Side Secret Injection**:
The provisioning seam in `SandboxLauncher` that retrieves encrypted environment secrets from the Central Environment Store (`env-store`), decrypts them in host or control-plane memory using `AGE_PRIVATE_KEY`, and mounts them directly as native process environment variables (`modal.Secret.from_dict()`) into the sandbox, guaranteeing master private keys and vault credentials never enter the container.
_Avoid_: Container decryption, in-sandbox sops, startup decryption

**In-Repo Secret Manifest (Legacy)**:
The transitional repository-tracked directory (`.secrets/`) containing SOPS-encrypted environment secret files and an `env.map` configuration file mapping encrypted source secrets to workspace destination paths (e.g. `app.env=.env`), decrypted during sandbox startup, maintained for backward compatibility and superseded by the Central Environment Store (`env-store`).
_Avoid_: Secret mapping, repo env files, host secret mount

**Hosted Sandbox Control Plane**:
A cloud-deployed Modal application (`sandbox-control-plane` in `sandbox/function.py`) serving both a FastAPI REST API (`/launch`, `/snapshot`, `/health`) authenticated via Bearer tokens (`MODAL_SANDBOX_AUTH_TOKEN`) and the embedded Sandbox Web Dashboard SPA (`/` and `/api/*`) authenticated via HTTP Basic Auth (`WEB_UI_USERNAME`, `WEB_UI_PASSWORD`), allowing external clients, the local CLI (`--remote`), and web browsers to inspect, provision, and manage sandboxes and snapshots across workspace profiles.
_Avoid_: Sandbox server, runner API, modal webhook daemon

**Sandbox Web Dashboard**:
A responsive single-page web management dashboard served by `sandbox/web.py` integrated into the Hosted Sandbox Control Plane (deployed via `modal deploy` or `modal serve sandbox/function.py`), protected by HTTP Basic Authentication, enabling real-time visual inspection, search and filtering, and termination of active sandboxes, as well as browsing, capturing, and deleting filesystem snapshots across configured Modal workspace profiles.
_Avoid_: Sandbox web UI, runner dashboard, sandbox console, modal GUI

**Snapshot Registry**:
A distributed catalog and metadata registry (`sandbox/snapshots.py`) tracking captured filesystem snapshots (including image ID, sandbox provenance, size, tags, and timestamps) backed by a named `modal.Dict` (`sandbox-snapshots`) with an automatic local JSON filesystem fallback (`~/.modal/sandbox-snapshots.json`).
_Avoid_: Snapshot catalog, snapshot db, snapshot list, modal dict store

**Multi-Profile Configuration**:
A Modal workspace discovery and client management service (`sandbox/profiles.py`) that discovers configured workspace profiles from `MODAL_TOKENS` in `.env` or `~/.modal.toml`, and supplies profile-scoped authenticated `modal.Client` instances to discover, query, and manage sandboxes and snapshots across multiple Modal environments.
_Avoid_: Modal profiles, multi-account setup, workspace selector

**T3 Code Persistent Storage Volume**:
A dedicated persistent Modal volume (`t3code-usage-v1` mounted at `/root/.t3-storage`) configured via `--t3-usage-volume` and toggled via `--no-t3-persist`, preserving Antigravity ACP conversation SQLite databases, T3 Code scan caches (`usage-scan-cache-v9.json`), model pricing rates (`usage-model-rates.json`), and multi-agent transcripts across ephemeral sandbox lifecycles.
_Avoid_: T3 volume, persistent disk, usage storage, transcript volume

**T3 Usage Synchronization Daemon**:
A bidirectional background synchronization service (`t3-usage-sync` in `shared/t3_usage_sync.py`) running inside T3 Code sandboxes that hydrates historical conversation databases and token accounting caches from `/root/.t3-storage` during container startup prior to `t3 serve`, and continuously flushes modified SQLite databases and caches atomically every 30 seconds and upon container exit traps (`SIGTERM`/`EXIT`).
_Avoid_: T3 sync daemon, usage daemon, transcript sync, storage syncer

**Developer CLI Tooling Precedence**:
The hierarchical resolution order governing developer CLI utility binaries and symlinks (`agyq`, `ghls`, `ghpr`, `ghclone`, `agyprofile`, `decrypt-repo-env`, `encrypt-repo-env`) inside Modal sandboxes: Workspace Repository (`$TARGET_DIR/scripts`) takes highest precedence, followed by Staged Dot Directory (`/root/.scripts`), falling back to the Pre-baked Base Image Binary (`/usr/local/bin`).
_Avoid_: Script priority, binary search path, cli override, tool priority

**Sandbox Launcher**:
A deep module (`sandbox/launcher.py`) that consolidates container configuration, image resolution, credential staging, Modal sandbox provisioning, network tunnel extraction, and SSH configuration into a single execution seam.
_Avoid_: Provisioning script, launch pipeline, sandbox runner core

**Running Sandbox**:
An encapsulated domain model returned by the Sandbox Launcher wrapping the provisioned `modal.Sandbox`, holding active network tunnels, credentials, and connection metadata, with projection into serializable API responses.
_Avoid_: Sandbox tuple, launch result, container handle
