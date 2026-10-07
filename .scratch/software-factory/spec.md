# Spec: Software Factory Assembly Line

Status: ready-for-agent

## Problem Statement

Software engineers wanting to automate feature development, bug fixing, and codebase maintenance lack a reliable, reproducible, and cost-effective assembly line. Existing autonomous agent loops suffer from compounding hallucinations, runaway token burn, lack of objective test verification, and uncoordinated git commits. Furthermore, running autonomous agents locally risks system modifications and requires dedicated machine uptime, while general cloud platforms lack zero-idle-cost ephemeral isolation and pre-baked developer toolchains. Developers need an isolated cloud-native software factory that can autonomously pick up structured tasks, implement them through specialized roles, verify them against real test suites, and deliver clean, tested git branches with zero manual babysitting.

## Solution

A cloud-native Software Factory operating as a Factory Hub that provisions ephemeral Modal Sandboxes to execute engineering tasks from target repositories' Local Markdown Issue Trackers.

A local Python launcher (`factory/run.py`) takes a target project name (`secrets/<project-name>`), feature slug, and optional issue ID, and provisions an isolated ephemeral Modal Sandbox with mounted factory harness code. Inside the sandbox, the target repository is cloned, smart branch detection checks out `factory/<feature>`, the repository is verified against the in-sandbox Pre-flight Guard (ensuring `/setup-matt-pocock-skills` configuration), and an Assembly Line Pipeline powered by the Pi Agent Harness (`@earendil-works/pi-agent-core`) executes specialized least-privilege stages:
1. **Planner Agent** (read-only): inspects the codebase, drafts `plan.md`, and discovers test commands.
2. **Coder Agent** (read/write/bash): writes implementation and reproduction tests on a shared Feature Branch (`factory/<feature>`).
3. **Deterministic Verifier**: executes test suites as a non-agentic test runner (exit codes cannot be hallucinated).
4. **Reviewer Agent** (read-only): audits the git diff and plan against repository standards.

If verification or review fails, a Self-Correction Loop feeds errors back to the Coder for up to 2 retries before escalating to `Status: ready-for-human`. Upon passing the Quality Gate, verified commits are pushed to the target remote, and the ticket is updated inline with `Status: resolved` and a comprehensive audit trail. An in-sandbox autonomous batch loop sequentially iterates through unblocked tickets on the frontier within the single warm sandbox.

## User Stories

1. As a software engineer, I want to define features and tickets in a Local Markdown Issue Tracker (`.scratch/<feature>/`) in the target repository's version control, so that my task specifications are co-located, offline-first, and tracked in Git.
2. As a software engineer, I want to run `python factory/run.py --project <project-name> --feature <slug> [--issue <id>]` from my terminal, so that the factory launches a sandbox to execute unblocked tickets on that project's frontier.
3. As a software engineer, I want autonomous feature batch execution inside a single warm sandbox, so that all unblocked tickets across a feature tree are sequentially executed, committed, and pushed with zero repeated container startup overhead.
4. As a factory operator, I want the factory runner to use Modal's direct Python client SDK (`modal.Sandbox.create`) with mounted factory code and the standard 16-hour execution timeout, so that jobs run reliably without deploying intermediate serverless worker applications.
5. As a security-conscious engineer, I want every ticket execution to run inside an ephemeral Modal Sandbox, so that untrusted code, external dependency installs, and agent tool commands are completely isolated.
6. As a developer, I want the factory to provision a fast Standard Sandbox by default and dynamically promote to a VM Sandbox when Docker daemon or swap memory is required, so that simple tasks launch in seconds while heavy builds retain full virtualization.
7. As a project owner, I want the factory to execute a Pre-flight Guard on checkout, so that jobs fail immediately with an actionable message if the target repository has not completed `/setup-matt-pocock-skills`.
8. As a maintainer, I want `software-factory`'s root `.scratch/` directory to be reserved strictly for modifying the factory itself, while target projects maintain their own independent `.scratch/` directories in version control.
9. As an engineer, I want the in-sandbox pipeline to use the Pi Agent Harness (`@earendil-works/pi-agent-core`), so that file reading, AST-safe editing, and terminal execution rely on a battle-tested coding engine.
10. As a factory operator, I want model inference to use my OpenCode Go subscription via `OPENCODE_GO_API_KEY` (decrypted from `secrets/opencode.env`), so that all stages use an active subscription without managing separate commercial vendor keys.
11. As an engineer, I want the assembly line to use a homogeneous flagship model (`DeepSeek V4.1 Flash` by default, or `MiMo-V2.6-Flash` via `--model mimo`), so that all stages maintain deep reasoning consistency without tool-calling degradation.
12. As a software architect, I want the Planner Agent to be strictly read-only, so that exploratory planning cannot accidentally modify code or corrupt the workspace before implementation begins.
13. As an engineer, I want the Coder Agent to write test-driven reproduction tests alongside feature code, so that bug fixes and requirements are objectively validated.
14. As a QA engineer, I want test execution to run through a Deterministic Verifier rather than an LLM, so that test passes are verified from process exit codes and logs rather than agent self-reporting.
15. As a code reviewer, I want an independent read-only Reviewer Agent to evaluate the git diff against the plan and domain standards, so that unvetted code cannot bypass the Quality Gate.
16. As a developer, I want a Self-Correction Loop that feeds test failures and review feedback back to the Coder for up to 2 retries, so that syntax errors, missing imports, or edge-case test failures are automatically fixed.
17. As a developer, I want persistent failures after 2 retries to escalate cleanly to `Status: ready-for-human`, so that agent tokens are conserved and humans can review the attached diagnostic trace.
18. As a team member, I want all tickets within a feature to commit to a shared Feature Branch (`factory/<feature>`), so that downstream tickets build upon earlier commits and the completed feature is consolidated on one reviewable branch.
19. As a developer, I want the ticket file (`.scratch/<feature>/issues/<NN>-<slug>.md`) to be updated inline with `Status: resolved`, commit SHA, target branch, and quality gate audit summaries, so that full provenance is captured in markdown.

## Implementation Decisions

- **Control Plane Architecture**: The Factory Runner is implemented as a direct Python script in `factory/run.py`, validating `secrets/<project-name>/fetch.env` locally and launching an ephemeral sandbox via `modal.Sandbox.create()` with mounted `sandbox/factory/` code and the standard 16-hour timeout from `sandbox/main.py`.
- **In-Sandbox Assembly Line & Batch Runner**: Implemented in TypeScript under `sandbox/factory/` using `@earendil-works/pi-agent-core` and `@earendil-works/pi-ai`, executed on the pre-baked Node.js 24 runtime inside the sandbox. It clones the target repository, checks out `factory/<feature>`, runs pre-flight checks, executes tickets sequentially on the frontier, pushes each resolved ticket to `origin factory/<feature>`, and halts immediately if retries fail.
- **Provider & Model Configuration**: Configured in `sandbox/factory/provider.ts` to connect to OpenCode Go using `OPENCODE_GO_API_KEY` (ephemerally decrypted at boot from `secrets/opencode.env`). Exclusively supports `DeepSeek V4.1 Flash` (default) and `MiMo-V2.6-Flash`.
- **Pre-flight Guard**: Implemented in `sandbox/factory/preflight.ts`. Validates that the target repository contains `.scratch/<feature>/spec.md`, root or domain `CONTEXT.md`, and issue tracking configuration before pipeline execution starts.
- **Role Permissions & Specialization**:
  - Planner: Given read-only file viewing, search, and directory navigation tools. Produces `plan.md` specifying files to touch, approach, and test commands.
  - Coder: Given file read, write, edit, and bash execution tools. Implements changes and commits to the feature branch.
  - Deterministic Verifier: Non-agentic runner executing the project's test suite via child processes. Captures stdout/stderr and exit codes.
  - Reviewer: Given read-only access to the diff, plan, and ticket. Produces a structured JSON review verdict.
- **Failure Recovery Policy**: Self-correction loop capped at 2 retries. On exceeding the retry budget, the ticket is marked `Status: ready-for-human` with error output appended under `## Comments`.
- **Feature Branch Strategy**: Commits accumulate on `factory/<feature>`. Upon successful ticket resolution, the branch is pushed to the target remote using the decrypted `GH_TOKEN`.

## Testing Decisions

- **Testing Seam**: The primary test seam is the In-Sandbox Pipeline Runner interface (`pipeline.ts` / `batch.ts`) and the Host Runner interface (`run.py`). The assembly line is treated as a deep module: callers provide a target project secret, feature slug, and optional ticket, and the pipeline executes the entire lifecycle behind this compact interface.
- **Good Test Criteria**: Tests must verify observable behavior:
  - Pre-flight guard aborts cleanly when given a repository missing `.scratch/` or `CONTEXT.md`.
  - Deterministic verifier accurately flags passing vs. failing test commands based on exit codes.
  - Self-correction loop retries up to 2 times on failing tests and terminates with `ready-for-human` on persistent failures.
  - Successful runs produce the expected git commit on the feature branch and update the ticket status to `resolved`.
- **Prior Art & Test Beds**: Existing tests in `projects/test1` and sandbox runner tests serve as prior art for executing commands within the environment. Local integration tests can run the pipeline directly against a test project fixture without requiring external GitHub credentials.

## Out of Scope

- Automated merging into `main` or `master` (merging is explicitly gated for human engineers).
- Web-based dashboards or graphical UIs (interactions are strictly through the CLI and `.scratch/` markdown files).
- Supporting commercial API keys directly outside the OpenCode Go subscription.
- Auto-generating specs for target repositories that have not completed `/setup-matt-pocock-skills`.

## Further Notes

- Architecture is governed by ADRs 0023, 0024, 0025, 0026, and 0027 in `docs/adr/`.
- Domain terminology is maintained in `CONTEXT.md`.
