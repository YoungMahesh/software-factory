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
A runtime development environment within the sandbox combining a pre-baked Python 3 runtime, an automated virtual environment (`.venv`) pre-installed with the Modal SDK and project dependencies, and opt-in decrypted Modal Client Credentials (`~/.modal.toml`) for developing and running Modal workloads from within the sandbox.
_Avoid_: Python tooling, python runner, modal env

**Shared Workspace Secret**:
The centralized Modal secret collection (`share0`) mounted into all sandboxes unconditionally, providing shared organizational secrets—specifically `AGE_PRIVATE_KEY` for SOPS bootstrap—used to decrypt Centralized Organization Credentials (`secrets/github-orgs.env`), the Cloudflare Tunnel token (`secrets/cloudflare.env`), In-Repo Secret Manifests, and opt-in agent/tooling credentials.
_Avoid_: Global secret, root secret, default secret

**Test Organization**:
The canonical GitHub organization (`sFactory0`) used with `test-` prefixed repositories configured with organization credentials used exclusively for automated pipeline verification and ephemeral integration testing.
_Avoid_: Test org, mock org, testing workspace

**Test Repository Baseline**:
The designated minimal test fixture repository (`sFactory0/test-live-test1`) used across automated live integration scripts to validate sandbox creation, secret decryption, and workspace initialization.
_Avoid_: Default test repo, test mock, dummy repo

**Sandbox Live Verification**:
An automated, ephemeral integration test procedure that provisions a live Modal sandbox against the Test Repository Baseline (`sFactory0/test-live-test1`), asserts container bootstrap and git clone invariants, exercises modified runner capabilities, and guarantees immediate sandbox termination upon completion.
_Avoid_: Manual live test, smoke run, sandbox healthcheck

**SOPS Decryption**:
A bootstrap mechanism during sandbox initialization that extracts `AGE_PRIVATE_KEY` from the Shared Workspace Secret (`share0`) to decrypt repository credentials and tooling configuration, purging encryption keys by default before user session handoff unless explicitly retained via `--sops`.
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
Common editor and AI agent configuration files tracked in the repository root `shared/` directory (`shared/opencode.json`, `shared/antigravity-settings.json`, `shared/antigravity-keybindings.json`, `shared/antigravity-onboarding.json`, `shared/pi-settings.json`, `shared/pi-models.json`, `shared/t3-keybindings.json`) and mounted into sandboxes at runtime.
_Avoid_: Sandbox config, local config, runner settings

**Sandbox Shell Aliases**:
A curated collection of interactive shell shortcuts for Docker and Git operations tracked in `shared/aliases.bash`, staged into sandboxes at `/root/.bash_aliases`, and automatically sourced in `~/.bashrc` across all sandbox runtime modes.
_Avoid_: Terminal shortcuts, bash aliases script, developer helpers

**Sandbox Git Configuration**:
Declarative global Git configuration and identity routing files tracked in `shared/gitconfig` and secondary identity profiles (e.g. `shared/gitconfig-mahesh471978`), staged into the Shared Base Image at `/root/.gitconfig` and `/root/.gitconfig-<identity>`, providing default authorship (`maheshghamand@gmail.com`) and conditional repository identity overrides (`includeIf`) without runtime shell mutation.
_Avoid_: Dynamic git config, inline git config, startup git config

**Modal Client Credentials**:
The authenticated client configuration and API token (`~/.modal.toml`) used by the Modal CLI and SDK to manage cloud resources. Decrypted with SOPS from `secrets/modal.toml` via `scripts/setup.sh --modal` (mode 0600), withheld from automated sandbox initialization by default to enforce credential isolation, and provisioned into sandboxes strictly when `--modal` is explicitly passed.
_Avoid_: Modal token, modal config, modal credentials

**OpenCode Credentials**:
A set of API keys and remote service tokens (`OPENCODE_GO_API_KEY`, `EXA_API_KEY`, `CONTEXT7_API_KEY`) encrypted with SOPS at `secrets/opencode.env` and decrypted inside the sandbox to `~/.config/opencode/opencode.env` (mode 0600) via `scripts/setup.sh --opencode`.
_Avoid_: OpenCode tokens, opencode keys, mcp secrets

**Shared Base Image**:
A cached Modal image definition built on Ubuntu 24.04 providing the foundational filesystem for both Standard Sandboxes and VM Sandboxes, pre-baked with common tooling including SSH server, SOPS, age, Git, ripgrep, tree, lsof, psmisc, fd, Python 3 (with venv and uv), Docker CLI binaries (including Buildx and Compose v2), Node.js 24, and pnpm.
_Avoid_: Base container, root image, runner image

**Browser Tooling**:
A pre-baked, headless Google Chrome instance installed by the `--browser` flag and shared by the Playwright and Chrome DevTools MCP servers, launched with the sandbox-free flags required when running as root.
_Avoid_: Browser MCP, headless browser setup, chrome layer

**Cloudflare Tunnel**:
A background ingress service (`cloudflared`) pre-baked into the Shared Base Image and installed as a service by default in the sandbox, authenticated via `CF_TOKEN` decrypted at boot from `secrets/cloudflare.env` using SOPS, securely routing external traffic from `https://3000.mahesh0.dev` directly to local port 3000 without requiring open inbound firewall ports.
_Avoid_: Cloudflare proxy, cloudflare daemon, cf tunnel

**Universal File Line Budget**:
A repository-wide size constraint requiring every production source file and executable automated test file to contain no more than 500 physical lines (`wc -l`).
_Avoid_: File size limit, code line limit, test budget, 500-line rule

**Centralized Organization Credentials**:
A single SOPS-encrypted file (`secrets/github-orgs.env`) containing GitHub Personal Access Tokens keyed by organization (e.g. `SFACTORY0_GH_TOKEN`), replacing legacy per-project secret folders and the deprecated `secrets_org/` directory.
_Avoid_: Org token file, github orgs secret, project fetch secret

**In-Repo Secret Manifest**:
A repository-tracked directory (`.secrets/`) containing SOPS-encrypted environment secret files and an `env.map` configuration file mapping encrypted source secrets to workspace destination paths (e.g. `app.env=.env`), decrypted during sandbox startup.
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
A Modal workspace discovery and client management service (`sandbox/profiles.py`) that parses `~/.modal.toml` (or `MODAL_CONFIG_PATH`), discovers configured workspace profiles, and supplies profile-scoped authenticated `modal.Client` instances to discover, query, and manage sandboxes and snapshots across multiple Modal environments.
_Avoid_: Modal profiles, multi-account setup, workspace selector

**T3 Code Persistent Storage Volume**:
A dedicated persistent Modal volume (`t3code-usage-v1` mounted at `/root/.t3-storage`) configured via `--t3-usage-volume` and toggled via `--no-t3-persist`, preserving Antigravity ACP conversation SQLite databases, T3 Code scan caches (`usage-scan-cache-v9.json`), model pricing rates (`usage-model-rates.json`), and multi-agent transcripts across ephemeral sandbox lifecycles.
_Avoid_: T3 volume, persistent disk, usage storage, transcript volume

**T3 Usage Synchronization Daemon**:
A bidirectional background synchronization service (`t3-usage-sync` in `shared/t3_usage_sync.py`) running inside T3 Code sandboxes that hydrates historical conversation databases and token accounting caches from `/root/.t3-storage` during container startup prior to `t3 serve`, and continuously flushes modified SQLite databases and caches atomically every 30 seconds and upon container exit traps (`SIGTERM`/`EXIT`).
_Avoid_: T3 sync daemon, usage daemon, transcript sync, storage syncer
