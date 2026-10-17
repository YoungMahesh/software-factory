# Modal Sandboxes

Isolated cloud development and execution environments running on Modal with agent and development tooling.

## Language

**VM Sandbox**:
A Modal sandbox execution environment configured with full virtual machine virtualization, custom kernel privileges, Docker daemon support, and swapfile allocation.
_Avoid_: Container sandbox, VM instance, Docker runner

**Standard Sandbox**:
A lightweight container sandbox on Modal running directly on the container runtime without virtualized hardware abstraction or Docker daemon capabilities.
_Avoid_: Basic sandbox, container VM

**Filesystem Snapshot**:
A point-in-time, copy-on-write capture of a Modal sandbox's root filesystem stored as a reusable `modal.Image` with an associated Time-To-Live (TTL), used to persist workspace state or accelerate subsequent sandbox cold starts without repeating repository cloning and dependency installation.
_Avoid_: Memory snapshot, container backup, sandbox image, VM snapshot


**OpenCode Server**:
A background web and agent server bound to a dedicated encrypted tunnel port, protected by a per-launch generated access password.
_Avoid_: OpenCode IDE, code server

**T3 Code Server**:
A background agent harness control surface running inside the sandbox (`t3 serve`), managing local CLI agents (Antigravity, OpenCode) across isolated Git worktrees, bound to a dedicated encrypted tunnel port.
_Avoid_: T3 IDE, t3 daemon, Theo agent runner, t3 web

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

**Organization Credentials**:
A directory containing a SOPS-encrypted GitHub fine-grained personal access token (`token`) and a declared permission manifest (`permissions.yml`) stored under `secrets_org/<org-name>/` providing scoped organizational access across member repositories.
_Avoid_: Org token, org secret, organization token

**Test Organization**:
A dedicated GitHub organization (`software-factory-09-test`) configured with organization credentials used exclusively for automated pipeline verification and ephemeral integration testing.
_Avoid_: Test org, mock org, testing workspace

**Test Repository Baseline**:
The designated minimal test fixture repository (`software-factory-09-test/test1`) used across automated live integration scripts to validate sandbox creation, secret decryption, and workspace initialization.
_Avoid_: Default test repo, test mock, dummy repo

**Sandbox Live Verification**:
An automated, ephemeral integration test procedure that provisions a live Modal sandbox against the Test Repository Baseline (`software-factory-09-test/test1`), asserts container bootstrap and git clone invariants, exercises modified runner capabilities, and guarantees immediate sandbox termination upon completion.
_Avoid_: Manual live test, smoke run, sandbox healthcheck

**Private-by-Default Repository Policy**:
The standard security convention where new target repositories instantiated via Factory Studio or the repository creation endpoints in the Test Organization (`software-factory-09-test`) are provisioned with private visibility on GitHub by default, with opt-out capability to create public repositories when explicitly declared.
_Avoid_: Public-by-default, default public repo, open test repos


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
Common editor and AI agent configuration files tracked in the repository root `shared/` directory (`shared/opencode.json`, `shared/antigravity-settings.json`, `shared/antigravity-keybindings.json`, `shared/antigravity-onboarding.json`) and mounted into sandboxes at runtime.
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

**Modal Application Tunnel**:
An ephemeral encrypted HTTPS tunnel provided by Modal (`sandbox.tunnels()[3000].url`) forwarding traffic to container port 3000, yielding a unique, collision-free preview URL per sandbox for interactive application testing in Factory Studio.
_Avoid_: Modal web tunnel, web url tunnel, preview port forward

**Dedicated Preview Sandbox**:
_Deprecated_: Superseded by Unified Studio Sandbox. Formerly an ephemeral Modal sandbox provisioned to build and serve a target application's active branch on port 3000 without executing the multi-agent assembly line.
_Avoid_: Dev runner, preview container, standalone server, test preview container

**Unified Studio Sandbox**:
A persistent Modal sandbox provisioned for an active repository in Factory Studio combining a background Vite development server bound to a Modal Application Tunnel on port 3000 with on-demand Assembly Line Pipeline execution via in-sandbox process execution (`sandbox.exec`).
_Avoid_: Dual sandbox, preview container, dev runner, split runner


**Software Factory**:
An automated software delivery system that ingests work items from an Issue Tracker, provisions ephemeral Modal Sandboxes, and executes a sequential multi-agent assembly line to implement and verify changes.
_Avoid_: Agent swarm, AI dev platform, autonomous loop

**Factory Orchestrator**:
A serverless Modal application that manages factory job lifecycles, dispatches ephemeral worker sandboxes, monitors stage transitions, and updates ticket states.
_Avoid_: Master runner, factory daemon, background coordinator

**Assembly Line Pipeline**:
A sequential workflow where specialized single-responsibility agents execute distinct stages with strict transition artifacts between them.
_Avoid_: Autonomous loop, dynamic swarm, generalist runner

**Issue Tracker Provider**:
An abstraction interface within the assembly line harness that decouples ticket discovery, claiming, and resolution from underlying storage engines (GitHub Issue Tracker or Local Markdown Issue Tracker).
_Avoid_: Ticket provider, tracker backend, issue driver

**GitHub Issue Tracker**:
A cloud-hosted task tracking convention that manages feature specifications and work items using GitHub Issues, Milestones, Labels, and Pull Requests. In Factory Studio, this serves as the sole convention for web UI operations.
_Avoid_: GitHub project, issue board, repo issues

**Local Markdown Issue Tracker**:
A filesystem-based task tracking convention that stores specifications and work items as markdown documents under `.scratch/<feature>/`. Used for CLI dispatchers, headless batch workflows, and internal Factory Hub development, but deprecated and excluded from web UI operations.
_Avoid_: Flat notes, scratchpad, local tickets

**Feature Pull Request**:
A GitHub Pull Request opened from a Feature Branch targeting `main` in Draft mode that aggregates sequential ticket commits and serves as the final human review and merge gate.
_Avoid_: PR review, factory PR, merge request

**Quality Gate**:
A multi-tier verification barrier requiring passing deterministic test suites, verified reproduction/acceptance tests, and independent automated review before a work item is marked resolved.
_Avoid_: CI check, validation pass

**Factory Hub**:
The central repository (`software-factory`) containing the serverless Factory Orchestrator and CLI Dispatcher. Its own `.scratch/` directory is strictly reserved for modifications to the software factory codebase itself, while all target projects maintain their own independent `.scratch/` directories or GitHub Issue Trackers.
_Avoid_: Master repo, factory workspace, coordinator root

**Target Project Workspace**:
The cloned repository within an ephemeral Modal Sandbox that contains its domain context documentation and is operated on by the assembly line harness.
_Avoid_: Remote repo, target directory, child workspace

**OpenCode Go Provider**:
The LLM inference provider authenticated via `OPENCODE_GO_API_KEY` from OpenCode Credentials, serving `MiMo-V2.6-Flash` and `DeepSeek V4.1 Flash` to the Pi Agent Harness inside the sandbox.
_Avoid_: OpenCode LLM, custom AI endpoint

**Autonomous Feature Batch**:
A continuous execution mode that sequentially claims, executes, and resolves all unblocked tickets on the frontier of a feature inside a single warm sandbox.
_Avoid_: Batch mode, multi-run, auto sweep

**Ticket Lifecycle**:
The end-to-end execution path of a work item through claiming, sandbox execution, quality gate verification, and resolution status updating.
_Avoid_: Issue flow, job run

**Self-Correction Loop**:
An automated feedback cycle where test execution logs or reviewer rejections are returned to the coding agent for up to two retry attempts before human escalation.
_Avoid_: Auto-heal loop, infinite retry

**CLI Dispatcher**:
The local command-line interface (`factory/run.py`) used to validate target project secrets (`secrets/<project-name>`), provision autonomous factory sandboxes, and stream progress logs.
_Avoid_: Job submitter, factory CLI

**Pi Agent Harness**:
The TypeScript execution framework based on `@earendil-works/pi-agent-core` that drives in-sandbox assembly line stages with pre-built file editing, search, and shell tools.
_Avoid_: Custom agent runner, python agent runner, generic LLM client

**Planner Agent**:
A read-only reasoning agent that analyzes the ticket, explores the codebase, and outputs a structured implementation plan.
_Avoid_: Architect, spec agent, design agent

**Coder Agent**:
The execution agent that consumes the plan and ticket, writes implementation and reproduction tests, and makes git commits on the feature branch.
_Avoid_: Developer agent, worker agent, programmer

**Deterministic Verifier**:
A non-agentic test execution stage that runs the target repository's automated test suites with bounded execution timeouts (60 seconds default) and captures exact exit codes and output logs. Strictly enforces non-interactive execution by filtering out long-running dev servers (`dev`, `serve`, `start`) and production builds that collide with active studio servers.
_Avoid_: Test agent, verification bot, QA agent

**Reviewer Agent**:
A read-only audit agent that compares the git diff and plan against repo standards and outputs a structured review verdict.
_Avoid_: Audit agent, QA bot, gatekeeper

**Feature Branch**:
A shared Git branch named `factory/<feature>` on the target repository where sequential ticket commits within a feature are accumulated and pushed for final review.
_Avoid_: Issue branch, task branch, temporary branch

**Pre-flight Guard**:
A validation check executed upon repository checkout in the sandbox verifying that domain prerequisites (`CONTEXT.md` or `GLOSSARY.md`, and active issue tracker configuration) are present before assembly line stages proceed.
_Avoid_: Healthcheck, bootstrap check, repo validator

**Factory Testing Console**:
_Deprecated_: Superseded by Factory Studio. Formerly an interactive local web interface running on the developer workstation used to configure and dispatch test parameters across ephemeral sandboxes. Consolidated into Factory Studio with the Studio Issue Drawer for execution controls and the Activity Drawer for multi-run history and telemetry.
_Avoid_: Factory UI, test dashboard, web runner, factory web app

**Factory Studio**:
An interactive web workspace providing a conversational prompt interface and live application preview for iteratively generating frontend applications on the Software Factory. Binds to port 3010 by default (overrideable via `PORT` environment variable) and is protected by HTTP Basic Authentication (`FACTORY_AUTH_USER` and `FACTORY_AUTH_PASS`), with a local development fallback (`admin`:`admin`) and startup warning.
_Avoid_: Factory UI, Lovable clone, app builder UI, prompt dashboard

**Cohere Editorial Design System**:
The enterprise design language implemented across Factory Studio inspired by Cohere's web interface, characterized by a stark white editorial canvas and soft stone secondary surfaces bounded by hairline containment rules, contrasted against high-contrast dark console execution blocks, monospaced technical telemetry, coral taxonomy chips, and pill-centric interactive controls.
_Avoid_: Dark mode dashboard, generic Tailwind theme, slate UI


**Studio Issue Drawer**:
A slide-over interface within Factory Studio that displays GitHub issues for the active repository, providing controls to inspect specifications, configure execution settings (model selection and VM sandbox virtualization), trigger the Grill-Before-Change Protocol, or directly dispatch the Assembly Line Pipeline.
_Avoid_: Issue panel, issue modal, GitHub view, issue selector

**Delivery Gate Card**:
A structured conversational card in Factory Studio Chat History summarizing Feature Pull Request status, resolved work items, and test verdicts, with controls to review and merge into main.
_Avoid_: PR card, merge card, gate message

**In-Studio Merge Control**:
An interactive control in Factory Studio that triggers a squash merge of a Feature Pull Request into main via the GitHub API, deletes the remote Feature Branch, and synchronizes the Unified Studio Sandbox.
_Avoid_: Merge button, quick merge, direct merge

**Agent Event Stream**:
A real-time structured telemetry channel emitting fine-grained LLM reasoning deltas, tool invocations, and execution outputs from the in-sandbox Pi Agent Harness across Modal container standard output into Factory Studio.
_Avoid_: Agent socket, LLM log stream, debug stream, thought pipe

**Grilling Assistant**:
A conversational reasoning service in Factory Studio that executes the `grilling` and `domain-modeling` protocols, interviewing the developer with structured question frontiers grounded in repository code facts, and drafting Architectural Decision Records (ADRs) conditionally before code changes are executed.
_Avoid_: Chat bot, prompt helper, grilling bot, interview agent

**Grill-Before-Change Protocol**:
An interactive requirement alignment workflow where user chat prompts in Factory Studio undergo interview rounds, codebase grounding, and domain terminology sharpening before synthesizing issues and dispatching the Assembly Line Pipeline.
_Avoid_: Manual interview, prompt delay, question loop

**Interactive Question Frontier**:
An interactive chat card in Factory Studio rendering Grilling Assistant questions with mutually exclusive option radio groups, custom override inputs, and an inline submission control that serializes developer decisions into chat history.
_Avoid_: Grill form, radio question card, option picker

**Repository Codebase Grounding**:
The autonomous discovery and inspection of target repository file trees and candidate component source code by the Grilling Assistant before generating interview questions, grounding requirement alignment in verified code facts rather than speculative assumptions.
_Avoid_: Static analysis, repo scanning, vector search

**Conditional ADR Policy**:
The requirement alignment principle ("Offer ADRs sparingly") where Architectural Decision Records (`docs/adr/`) are drafted strictly for changes introducing irreversible or fundamental architectural trade-offs, omitting draft ADRs (`draft_adr: null`) for localized component edits, deletions, bug fixes, and styling adjustments.
_Avoid_: Universal ADR, mandatory ADR, indiscriminate ADR

**Prompt Archetype**:
A classification heuristic (`deletion`, `component_modification`, `styling`, `new_feature`) used by the Grilling Assistant to tailor interview questions to the developer's intent and prevent irrelevant routing or architectural proposals.
_Avoid_: Prompt category, intent tag, prompt type

**Externalized Prompt Templates**:
Dedicated, version-controlled markdown files (`.md`) colocated within their execution runtime directories (`factory/ui/grill/prompts/` and `sandbox/factory/harness/prompts/`) that define LLM system personas, operational constraints, and JSON schemas, parsed with double-curly brace (`{{variable}}`) substitution and cached in memory to eliminate string escaping collisions with JSON schemas and prevent code file bloat.
_Avoid_: Hardcoded prompts, inline prompt strings, prompt constants, raw prompt templates

**Inference Error Turn**:
An explicit conversational turn emitted when remote LLM inference encounters a network, authentication, or provider failure, persisted to Studio Chat History and rendered with diagnostic details and a retry trigger instead of silently falling back to mock responses.
_Avoid_: Silent fallback, mock error, failed message

**Target Project Skills**:
The suite of Matt Pocock engineering skills (`.agents/skills/`), domain glossary (`CONTEXT.md`), architectural records (`docs/adr/`), and agent configurations (`docs/agents/`) scaffolded into every application developed on the Software Factory.
_Avoid_: Target skills, repo configs, agent templates

**Canonical Template Repository**:
The reference GitHub repository (`software-factory-09-test/tanstack-start-template`) providing a minimal, unencumbered TanStack Start SPA starter used as the baseline for instantiating new applications in Factory Studio.
_Avoid_: Base repo, default repo, starter repo, app seed

**Template Provisioning Readiness**:
The operational state of a newly generated GitHub repository where asynchronous template file replication has completed, establishing a valid HEAD commit and default branch reference (`main`) before Target Project Skills and architectural decision records are committed.
_Avoid_: Repo ready, git sync, template wait, repo bootstrap status

**ADR Quality Gate**:
A mandatory verification check during the Pre-flight Guard and Reviewer Agent stage ensuring that `docs/adr/` exists and that implementation diffs strictly adhere to all accepted architectural decisions.
_Avoid_: ADR check, architecture test

**Studio Database**:
A cloud-hosted libSQL database (backed by Turso) connected directly over TLS that stores Factory Studio Chat History, Job records, and Agent Telemetry Logs in development and production environments, while utilizing an in-memory SQLite database (`:memory:`) for automated test isolation.
_Avoid_: Local DB, chat database, studio cache

**Studio Chat History**:
The durable chronological sequence of user prompts, Grilling Assistant question frontiers, developer responses, and approved plan cards associated with a target repository.
_Avoid_: Prompt log, conversation memory, message cache

**Agent Telemetry Log**:
A durable database record capturing structured events (stage transitions, tool invocations, model reasoning deltas) and standard output console streams emitted during Assembly Line Pipeline execution, indexed by Job ID.
_Avoid_: Run log, container output, worker debug

**Live Preview Branch Selector**:
An interactive dropdown control in the Factory Studio Live Preview toolbar displaying the active Git branch and allowing developers to switch between `main` and active `factory/<feature>` branches in place via `sandbox.exec` without container teardown.
_Avoid_: Branch pill, branch toggle, git dropdown, preview branch switcher

**Trunk Synchronization**:
An interactive and in-place container git orchestration mechanism in Factory Studio that synchronizes the Unified Studio Sandbox with the default trunk branch (`main`), pulling latest remote commits via `sandbox.exec`, resolving dependency drift, and refreshing the Live Preview without container restart.
_Avoid_: Auto-pull, git sync daemon, background fetcher, main updater

**Turn Rollback**:
The atomic reversal of a completed code-producing conversational turn in Factory Studio, reverting its feature branch commit, synchronizing the Unified Studio Sandbox dev server in place, reopening the associated work item, and recording an append-only rollback event in Studio Chat History.
_Avoid_: Undo turn, revert version, turn reset, conversational rewind

**Universal File Line Budget**:
A repository-wide size constraint requiring every production source file and executable automated test file to contain no more than 500 physical lines (`wc -l`).
_Avoid_: File size limit, code line limit, test budget, 500-line rule

**Test Suite Decomposition**:
The structural partitioning of a monolithic test file into a modular directory package or focused subsystem test modules adhering to deep module principles without altering test coverage.
_Avoid_: Test splitting, test refactor, test slicing, test modularization

**Command Failure Diagnostics**:
A dedicated telemetry inspection surface in Factory Studio's Activity Drawer that captures, isolates, and displays non-zero exit code shell executions from both the Coder Agent and Deterministic Verifier stages to facilitate diagnosing missing environment dependencies and refining agent system prompts.
_Avoid_: Error tab, failed bash tab, debug view, command log

**Agent Bottleneck Profiler**:
A dedicated performance profiling surface in Factory Studio's Activity Drawer and REST API that measures, ranks, and categorizes execution durations across agent shell commands, verifier test runs, and LLM thinking phases within an active job and aggregated across historical repository runs.
_Avoid_: Slow command log, performance tab, latency viewer, bottleneck tracker

**Infrastructure Bottleneck Heuristics**:
Pattern-matching categorization rules that classify agent command executions and telemetry events into discrete infrastructure domains (`Package Install`, `Test Suite`, `Build / Compile`, `Git / VCS`, `LLM Thinking`) based on executable binaries, CLI arguments, and pipeline stages to isolate systemic pipeline latency.
_Avoid_: Command classifier, category heuristics, bottleneck badges, command tagging

**Clean Canvas Invariant**:
The architectural guarantee across the Canonical Template Repository, Assembly Line Agent prompts, ticket synthesis, and quality gates requiring generated web applications to start with an empty, unencumbered route container and neutral branding baseline, ensuring autonomous agents cleanly overwrite placeholder markup rather than appending components beneath template boilerplate cards.
_Avoid_: Blank screen, bare canvas, empty starter, template leftover


