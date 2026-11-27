# Software Factory

Cloud development environments, persistent application resources, and the application starter shared across the factory.

## Language

**VM Sandbox**:
A Modal sandbox execution environment configured with full virtual machine virtualization (`runtime="vm"`), custom kernel privileges, Docker daemon support, burstable RAM `(128, 16384)` MiB identical to Standard Sandboxes, and swapfile allocation.
_Avoid_: Container sandbox, VM instance, Docker runner

**Standard Sandbox**:
A lightweight container sandbox on Modal running directly on the container runtime without virtualized hardware abstraction or Docker daemon capabilities.
_Avoid_: Basic sandbox, container VM

**Standalone Sandbox**:
A development sandbox with an empty Git workspace and no Target Repository clone. Its instance identity is distinct from the requested application name.
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

**Control Plane Provenance**:
The Git commit SHA, short hash, Git ref, and clean/dirty working tree status of the `software-factory` repository captured directly from the local Git repository at deployment time (`modal deploy` or `modal serve`), injected into the Modal control plane function secrets, and displayed in the management Web UI header.
_Avoid_: Function version, runner hash, app tag

**Shallow Repository Clone**:
A Git checkout optimization in development sandboxes that truncates commit history on the target branch to a fixed maximum depth of 50 commits, accelerating container boot latency and saving network transfer while maintaining sufficient recent history for active development.
_Avoid_: Partial clone, shallow branch, depth clone, truncated repo

**Full Git Clone**:
An opt-in Git checkout configuration (`--full-clone`) in development sandboxes that downloads all commits of the target branch during container provisioning, bypassing the shallow clone depth limit for workflows requiring complete commit histories.
_Avoid_: Unshallow clone, complete fetch, deep repo

**Filesystem Snapshot**:
A point-in-time, copy-on-write capture of a Modal sandbox's root filesystem stored as a reusable `modal.Image` with an associated Time-To-Live (TTL), used to persist workspace state or accelerate subsequent sandbox cold starts without repeating repository cloning and dependency installation.
_Avoid_: Memory snapshot, container backup, sandbox image, VM snapshot

**OpenCode Provider**:
An internal AI agent provider spawned by T3 Code (`/root/.opencode/bin/opencode`) inside `--t3` containers. The standalone OpenCode web server daemon (`opencode serve`) and port 4096 tunnel (`--opencode`, `--opencode-port`) are retired.
_Avoid_: OpenCode server, OpenCode IDE, code server

**T3 Code Server**:
A background agent harness control surface running inside the sandbox (`t3 serve`), managing local CLI agents across isolated Git worktrees, bound to a dedicated encrypted tunnel port.
_Avoid_: T3 IDE, t3 daemon, Theo agent runner, t3 web

**Codex Provider**:
The OpenAI coding agent available through T3 Code in a sandbox.

**Codex Credential Profile**:
One reusable ChatGPT sign-in session for the Codex Provider. Multiple profiles can belong to the same ChatGPT account, and each profile can serve one running sandbox at a time.
_Avoid_: Modal profile, ChatGPT account

**Pairing URL**:
The public HTTPS URL emitted by T3 Code (`t3 pair` or sandbox launch metadata) containing the Modal application tunnel domain and a cryptographically generated pairing token (`https://<sandbox-tunnel>.modal.host/pair#token=...`), enabling external browser and desktop app pairing with the remote T3 Code Server.
_Avoid_: Local pairing URL, private IP link, direct socket URL, t3code link

**Herdr Multiplexer (Retired)**:
The legacy agent-aware terminal multiplexer previously provisioned via `--herdr`, retired in favor of T3 Code multi-worktree orchestration.
_Avoid_: Terminal multiplexer, tmux clone, herdr daemon, herdr runner

**Pi Coding Agent CLI (Retired)**:
The terminal coding agent previously provisioned via `--pi`, retired in favor of T3 Code agent orchestration.
_Avoid_: Pi agent, pi terminal, pi runner

**Antigravity Provider**:
Google Gemini agent provider orchestrated inside `--t3` sandboxes via T3 Code's managed Agent Client Protocol (ACP) runtime (`antigravity` CLI running `antigravity acp`), with lightweight query (`agyq`) and profile management (`agyprofile`) CLI utilities. The standalone Antigravity CLI binary and `--agy` launch flag are retired.
_Avoid_: Antigravity CLI, Gemini CLI, antigravity-ide

**Antigravity Remote Control (Retired)**:
The legacy background daemon (`agy remote-control start`) previously running under `--agy`, retired in favor of T3 Code's web and mobile pairing surfaces.
_Avoid_: Antigravity web, agy proxy, remote tunnel

**React Native Tooling**:
A pre-baked Android and React Native development toolchain within the sandbox image including OpenJDK 17, Android SDK platforms, build-tools, NDK, CMake, Watchman for file indexing, a tuned inotify file watch limit (524,288), and `@expo/ngrok` for tunnel connectivity.
_Avoid_: Android environment, mobile dependencies, Android emulator

**Metro Tunnel**:
A secure HTTPS tunnel forwarding traffic directly to the React Native or Expo Metro bundler development server running inside the sandbox.
_Avoid_: Metro proxy, bundler forward, mobile tunnel

**Modal Development Tooling**:
The opt-in Python development environment and authenticated Modal access provided inside a sandbox.
_Avoid_: Python tooling, python runner, modal env

**Factory Environment Configuration**:
The local factory settings and credentials used to configure control plane deployment and sandbox launches.
_Avoid_: Config file, root env, secret bundle

**Shared Workspace Secret (Retired)**:
A retired shared credential source used by earlier sandbox provisioning. Current provisioning resolves factory configuration and the Central Config Store.
_Avoid_: Global secret, root secret, default secret

**Test Organization Scope**:
The configured GitHub organization that owns the Test Repository Baseline.
_Avoid_: Test org, mock org, testing workspace

**Test Repository Baseline**:
The `software-factory` repository under the configured `GH_ORG_NAME` used for Sandbox Live Verification.
_Avoid_: Default test repo, test mock, dummy repo

**Sandbox Live Verification**:
An ephemeral integration test against the Test Repository Baseline that checks sandbox startup and exercises changed capabilities. The test sandbox terminates immediately after verification.
_Avoid_: Manual live test, smoke run, sandbox healthcheck

**SOPS Decryption**:
The recovery of plaintext repository secrets from encrypted vault files using an authorized Age key. It occurs on the machine fetching the secrets, including the launch host during sandbox provisioning.
_Avoid_: Sops setup, age injection, secret script

**Tooling Setup Script**:
The factory utility that configures credentials and account profiles for selected development tools.
_Avoid_: Repo setup script, secret decrypter, install script

**Modal Sandbox SSH Key**:
The dedicated client key pair used to authenticate SSH access to development sandboxes. Operators select the authorized public key and maintain the matching private key separately.
_Avoid_: Default SSH key, id_ed25519, root SSH key

**Antigravity OAuth Token**:
The authenticated account credential used by the Antigravity provider and its account profiles.
_Avoid_: Gemini token, antigravity auth token, cli token

**Shared Agent Configuration**:
Factory-maintained editor and agent settings included in development sandbox images.
_Avoid_: Sandbox config, local config, runner settings

**Shared Agent Skills**:
Factory-maintained agent skills available across workspaces in every fresh sandbox. A sandbox resumed from a Filesystem Snapshot retains the skill set captured in that snapshot.

**Sandbox Shell Aliases**:
Factory-maintained interactive shortcuts for common Docker and Git operations inside sandboxes.
_Avoid_: Terminal shortcuts, bash aliases script, developer helpers

**Sandbox Git Configuration**:
The shared Git defaults and repository-specific authorship applied inside development sandboxes.
_Avoid_: Dynamic git config, inline git config, hardcoded git config

**Sandbox Timezone Configuration**:
The selected timezone used by a sandbox and its development tools, with factory defaults and optional repository-specific overrides.
_Avoid_: Hardcoded UTC, container clock hack, inline tz

**Cloudflare Tunnel Domain**:
The public application hostname associated with a configured sandbox Cloudflare tunnel. Displaying the hostname does not establish its DNS or routing.
_Avoid_: Static tunnel URL, hardcoded tunnel domain

**Modal Client Credentials**:
The account profile credentials that authorize Modal operations from a launch host or an enabled sandbox development environment.
_Avoid_: Modal token, modal config, modal credentials

**OpenCode Credentials**:
The provider keys and service tokens used by OpenCode within the T3 Code integration.
_Avoid_: OpenCode tokens, opencode keys, mcp secrets

**Shared Base Image**:
The single cached Ubuntu 24.04 Modal image shared across Standard Sandboxes and VM Sandboxes as their foundational filesystem, pre-baked with Python 3.12, Node.js 24, pnpm 10, `uv`/`uvx`, pinned `ruff`, `cloudflared`, `sops`, `gh`, Docker CLI/Compose v2, database clients, and core CLI utilities.
_Avoid_: Base container, root image, runner image

**Browser Tooling**:
Pre-baked headless Chromium installed by Playwright (`uvx playwright install --with-deps chromium`) when `--browser` or `--t3` is enabled (with `/opt/t3/t3 browser setup` added for `--t3`). Separately, `--xfce` installs full Google Chrome (`google-chrome-stable`) with sandbox-free flags for graphical desktop VMs.
_Avoid_: Browser MCP, headless browser setup, chrome layer

**Cloudflare Tunnel**:
The authenticated application ingress connecting a sandbox web service to a configured public hostname.
_Avoid_: Cloudflare proxy, cloudflare daemon, cf tunnel

**Universal File Line Budget**:
The maximum physical line count for production code and executable Python tests in the Execution Plane, with the exemptions defined by repository standards.
_Avoid_: File size limit, code line limit, test budget, 500-line rule

**Centralized Organization Credentials**:
The single-organization GitHub access configuration defined via `GH_TOKEN` and `GH_ORG_NAME` in the Factory Environment Configuration (`.env`), replacing legacy multi-file secret bundles (`secrets/github-orgs.env`).
_Avoid_: Org token file, github orgs secret, project fetch secret

**Central Config Store**:
A single private GitHub repository (`config` under `${GH_ORG_NAME}`) housing SOPS-encrypted environment files (`env/<repo>/`), plaintext Host Ingress Proxy configurations (`caddy/<profile>/`), **Idea Notes** (`scratchpad/<slug>.md`), and **Raw Notes** (`raw/<slug>.md`). Supersedes the retired `env-store` and `caddy-store` repositories.
_Avoid_: Central secrets repo, env-store, caddy-store, config bucket, secret bucket

**Environment Mapping Manifest (`env.map`)**:
A plaintext configuration manifest located in `config/env/<repo>/env.map` (and cached locally in `.git/env-vault/env.map`) that maps source secret files to relative workspace destination paths (e.g. `web.env=apps/web/.env`, `api.env=packages/api/.env.local`) for monorepo architectures.
_Avoid_: Secret manifest, env config, dotenv map

**Repository Vault Cache (`.git/env-vault/`)**:
The untracked directory located inside the parent repository's common Git directory (`$(git rev-parse --git-common-dir)/env-vault`) that securely caches decrypted runtime secrets (`default.env`, `web.env`) and destination mapping manifests (`env.map`) outside Git version control, accessible to all linked worktrees without requiring `.gitignore` entries.
_Avoid_: In-repo secrets, git secret cache, worktree dot directory

**Git Worktree Environment Propagation**:
The automated mechanism powered by Git's global `post-checkout` hook (`core.hooksPath = /root/.git-hooks`) that detects newly checked out worktrees in T3 Code Web UI (`git worktree add`) and non-destructively copies decrypted environment files from `.git/env-vault/` into the worktree root or subproject paths with restricted `0600` permissions.
_Avoid_: Worktree env copying, manual worktree env, worktree secret sync

**Host-Side Secret Injection**:
The provisioning step that decrypts repository vault data on the launch host and supplies it to a sandbox. Factory credentials can also be propagated into that sandbox.
_Avoid_: Container decryption, in-sandbox sops, startup decryption

**Modal Secret Injection**:
The delivery of sensitive values to a runtime through Modal Secrets. Tools can persist the delivered values in files, so injection does not imply credential-free snapshots.
_Avoid_: Secret mounting, file-based secrets, container secret staging, disk secrets

**Host Environment Whitelist**:
The explicit set of ambient host configuration keys accepted as fallbacks during secret collection. Factory environment files have a separate propagation path.
_Avoid_: Environment dump, full env export, host env pass-through

**In-Repo Secret Manifest (Legacy)**:
A retired repository-local mapping of encrypted files to workspace destinations, superseded by the Central Config Store manifest.
_Avoid_: Secret mapping, repo env files, host secret mount

**Hosted Sandbox Control Plane**:
The Modal-hosted FastAPI backend (`sandboxes/sandbox/function.py`), Durable Launch Coordinator (`run_launch_request`), and serialized Factory State Authority (`factory-state-v1`) that provision and manage development sandboxes, Prime Sandboxes, Factory Apps, snapshots, and Scratchpad caches. Separate from the Resource Plane persistence console.
_Avoid_: Sandbox server, runner API, modal webhook daemon

**Sandbox Web Dashboard**:
The Next.js 16 + React 19 browser UI and same-origin BFF proxy (`dashboard/apps/web`) hosted on the VPS for building Factory Apps, inspecting active sandboxes (with live lifespan timers and accrued Modal costs), managing snapshot registry records, and authoring Scratchpad Ideas/Raw notes. Runs as an isolated production apex instance (`/opt/sandbox-dashboard`) on the App Base Domain and an isolated staging instance (`/opt/sandbox-dashboard-staging`) on `dashboard.<APPS_BASE_DOMAIN>`.
_Avoid_: Sandbox web UI, runner dashboard, sandbox console, modal GUI

**Snapshot Registry**:
The catalog of captured filesystem image identifiers and their associated sandbox metadata. Removing a catalog entry does not delete the retained image.
_Avoid_: Snapshot catalog, snapshot db, snapshot list, modal dict store

**Snapshot Lifecycle**:
The unified operational sequence managed by `sandbox/snapshots.py` that synchronizes filesystem buffers (`sync`), detects virtual machine runtime capabilities, captures copy-on-write root filesystem images, records metadata in the Snapshot Registry, and optionally terminates the source sandbox container.
_Avoid_: Snapshot process, snapshot pipeline, snapshot flow

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
The hierarchical resolution order governing developer CLI utility binaries and symlinks (`agyq`, `ghls`, `ghpr`, `ghclone`, `agyprofile`, `push-repo-env`, `pull-repo-env`) inside Modal sandboxes: Workspace Repository (`$TARGET_DIR/scripts`) takes highest precedence, followed by Staged Dot Directory (`/root/.scripts`), falling back to the Pre-baked Base Image Binary (`/usr/local/bin`).
_Avoid_: Script priority, binary search path, cli override, tool priority

**Sandbox Launcher**:
A deep module (`sandbox/launcher.py`) that consolidates container configuration, image resolution, credential staging, Modal sandbox provisioning, network tunnel extraction, and SSH configuration into a single execution seam.
_Avoid_: Provisioning script, launch pipeline, sandbox runner core

**Running Sandbox**:
An encapsulated domain model returned by the Sandbox Launcher wrapping the provisioned `modal.Sandbox`, holding active network tunnels, credentials, and connection metadata, with projection into serializable API responses.
_Avoid_: Sandbox tuple, launch result, container handle

**Documentation Web App**:
A dedicated, standalone Modal App (`modal-sandboxes-docs` defined in `sandbox/docs.py`) serving the compiled static documentation site (compiled with Zensical) as a public, serverless ASGI web function via `@modal.asgi_app()`, decoupling documentation delivery from the Hosted Sandbox Control Plane.
_Avoid_: Docs server, control plane docs, mkdocs runner, documentation container

**XFCE Desktop Sandbox**:
A Modal sandbox execution environment configured with an XFCE 4 desktop environment, TigerVNC server, and Google Chrome (`--xfce`), automatically backed by a VM Sandbox with burstable RAM `(128, 16384)` MiB, `/dev/shm`, and full Linux kernel compatibility, managed via `desktop-service`.
_Avoid_: GUI sandbox, VNC runner, X11 container

**noVNC Web Ingress**:
The browser access path for interacting with a sandbox graphical desktop through noVNC.
_Avoid_: VNC web, noVNC proxy, desktop web UI

**Resource Plane**:
The persistence subsystem that manages application databases, object storage, their credentials, and a web console and management API.
_Avoid_: Database host, db server, storage runner, backend container

**ResourcePlaneClient**:
The factory client for Resource Plane management operations, including project scope, credential retrieval, and database certificate discovery.
_Avoid_: MCP client, db-host transport, postgres helper, rpc caller

**Execution Plane**:
The cloud sandbox execution subsystem (`sandboxes/`) running on Modal infrastructure that provisions on-demand, isolated Linux environments with developer and agent tooling.
_Avoid_: Runner plane, container layer, compute worker

**Resource Plane Deployment Pipeline**:
The remote infrastructure automation mechanism that uses SSH credentials configured in the environment to connect to a target VPS, verify Docker daemon dependencies, and execute deployment orchestration remotely, strictly decoupled from runtime sandbox access.
_Avoid_: SSH runner, remote script, vps agent

**Host Ingress Proxy**:
The shared reverse-proxy service running on a VPS alongside the Resource Plane that owns host HTTP/HTTPS ports, manages public ACME TLS certificates, and routes external domain traffic to the Resource Plane and any co-located host applications. Configuration backups are stored in the Central Config Store under `caddy/<profile>/`.
_Avoid_: App proxy, caddy server, edge proxy, reverse-proxy container

**In-Repo Secrets Directory**:
An uncommitted, Git-ignored directory at the repository root (`.secrets/`) used to store local credentials and private keys that cannot be stored in `.env`, synchronized to the Central Config Store (`env/`) via `push-repo-env` and `pull-repo-env`.
_Avoid_: Local keys, private folder, uncommitted secrets, key cache

**DbHostClient**:
A deep control plane client module (`sandbox/db_host_client.py`) that encapsulates JSON-RPC over HTTP communication with the db-host MCP server, managing admin authentication, project scoping, and root CA certificate caching behind a cohesive transport seam.
_Avoid_: MCP client, db-host transport, postgres helper, rpc caller

**EnvStoreVault**:
A domain adapter and vault client module (`sandbox/env_store.py`) that encapsulates target repository secret resolution from the Central Config Store (`env/<repo>/`), SOPS decryption, manifest parsing, and bundle packaging, exposing symmetric push/pull and sandbox bundle projection seams.
_Avoid_: Secret fetcher, vault script, env parser, sops helper

**FactoryConfiguration**:
A centralized configuration and credentials discovery module (`sandbox/config.py`) that encapsulates multi-path `.env` resolution, host environment inspection, and Modal secret compilation into cohesive domain models (`FactoryConfiguration` and `FactoryCredentials`).
_Avoid_: Config parser, dotenv reader, creds loader, secret scanner

**App Template**:
The canonical starter application blueprint maintained in the factory from which new full-stack web and optional mobile projects are created.
_Avoid_: Base template, starter kit, boilerplate

**App Scaffolder**:
The first-party tooling that materializes the App Template into a new application workspace and optionally wires repository creation, persistence resources, secrets, and sandbox launch.
_Avoid_: Project generator, bootstrap script, create-base-app


**App Base Domain**:
The configured root DNS domain (`APPS_BASE_DOMAIN`) whose wildcard TLS certificate covers the apex Sandbox Web Dashboard, its staging subdomain (`dashboard.<APPS_BASE_DOMAIN>`), and subdomains assigned to Hosted Apps on the VPS.
_Avoid_: Root domain, tunnel domain, resource plane domain

**Hosted App**:
A scaffolded application deployed alongside the Resource Plane on the VPS (`/root/<repo-name>`) and exposed on a subdomain of the App Base Domain through the Host Ingress Proxy. Each Hosted App owns its deployment directory, container identity, and route. Redeployment and teardown must identify the same app, and distinct apps cannot share those claims.
_Avoid_: Live app, production sandbox, VPS app

**Factory App**:
An application or repository workspace launched from the builder homepage, linking its target workspace (scaffolded template, blank Git repo, or T3-managed Git worktree on a shared GitHub repository checkout), optional initial prompt, optional Resource Plane resources, Modal sandbox, T3 Code Server thread, and optional Hosted App. Cards are automatically removed when their backing sandbox terminates.
_Avoid_: Builder project, prompt project, user app

**Repository Catalog Cache**:
A control-plane snapshot of accessible GitHub repositories persisted across dashboard loads and updated only when an operator explicitly triggers a refresh.
_Avoid_: Repo cache, github cache, repo store

**Launch Request**:
A single idempotent provisioning attempt to create or reopen a Factory App, tracking request status, workspace metadata, Modal sandbox handle, and T3 Code Server thread identity.
_Avoid_: Build job, prompt job, start request

**Prime Sandbox**:
A long-lived, multi-tenant Modal sandbox provisioned lazily on demand and partitioned by runtime capabilities (`profile`, **VM Sandbox** mode, Mobile/React Native, and sandbox flags) that hosts multiple Factory Apps and T3 Code Server threads concurrently, eliminating container startup overhead for subsequent prompts.
_Avoid_: Shared sandbox, warm sandbox, master sandbox, persistent container

**Scratchpad**:
The note-capture surface in the Sandbox Web Dashboard (`/scratchpad`) partitioned into **Ideas** (AI-assisted refinement with review before commit) and **Raw** (direct verbatim Git commit without AI). Operators can browse, read, copy, delete, and send notes from either section into the Builder composer.
_Avoid_: Memo tab, notepad, prompt history, draft buffer

**Idea Note**:
An AI-refined Markdown note stored under `scratchpad/<slug>.md` in the Central Config Store (`config`), formatted with a `# <Title>` heading and collision-disambiguated filename on explicit user confirmation.
_Avoid_: Brainstorm doc, quick note file, markdown memo, scratchpad note

**Raw Note**:
An unedited UTF-8 note committed directly from the **Raw** section to `raw/<slug>.md` in the Central Config Store (`config`) without AI transformation or review modal, using an optional title solely for `<slug>.md` naming.
_Avoid_: Unrefined note, raw idea, direct dump, scratchpad note

**Scratchpad Catalog Cache**:
A persisted index of **Idea Note** and **Raw Note** metadata (and lazily cached note bodies) retained across dashboard loads and updated on UI commits or explicit operator refresh.
_Avoid_: Notes cache, scratchpad store, github notes cache

**Factory State Authority**:
The sole owner of durable Factory App, Launch Request, Prime Sandbox, **Repository Catalog Cache**, and **Scratchpad Catalog Cache** state, coordinating competing requests and enforcing ownership transitions.
_Avoid_: State server, volume lock, metadata backend
