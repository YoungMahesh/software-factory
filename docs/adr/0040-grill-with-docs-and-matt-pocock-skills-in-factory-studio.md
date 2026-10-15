# Grill-with-Docs Conversational Protocol and Matt Pocock Skills in Factory Studio

**Status**: Accepted

To align user intent, eliminate silent assumptions, and maintain architectural integrity across all applications developed on the Software Factory, we decided to implement the **Grill-Before-Change Protocol** in Factory Studio and establish **Target Project Skills** (including Architectural Decision Records) across all generated repositories.

## Considered Options

- **Immediate Autonomous Assembly Line Execution per Prompt**: Directly converting every user chat prompt into GitHub issues and executing code changes immediately (prior behavior). Rejected because vague or underspecified prompts lead to architectural misalignment, incorrect assumptions, wasted sandbox compute, and untracked architectural decisions.
- **In-Sandbox Blocking Interview Stage**: Spawning a Modal sandbox immediately and running an interactive Grilling Agent inside the container that blocks execution while waiting for user SSE chat inputs. Rejected because holding live cloud sandboxes during human deliberation wastes compute, incurs container timeouts, and adds latency to conversation turns.
- **In-Studio Conversational Turn with Target Project Skills and ADR Quality Gate**: Running an interactive Grilling Assistant directly within Factory Studio's web conversation layer that stress-tests requirements in structured question rounds, drafts ADRs in markdown, and waits for explicit user plan approval before provisioning sandboxes or dispatching the Assembly Line Pipeline. In addition, every target application repository is scaffolded with Matt Pocock's engineering skills (`.agents/skills/`), `CONTEXT.md`, and `docs/adr/`, with the Assembly Line Pipeline enforcing ADR compliance during planning and review. Accepted because it delivers sub-second conversational feedback, produces durable architectural documentation, and ensures code changes strictly adhere to agreed architectural decisions.

## Consequences

- The canonical terms **Grilling Assistant**, **Grill-Before-Change Protocol**, **Target Project Skills**, and **ADR Quality Gate** are incorporated into `CONTEXT.md`.
- **Factory Studio Conversational Workflow**:
  - Chat prompts in Factory Studio activate the Grilling Assistant by default (with an optional fast-build bypass toggle in `PromptComposer` for trivial modifications).
  - The Grilling Assistant formats interview turns using structured question frontiers with recommended answers (`❓ Q1 ... ➡️ recommended answer`), stress-testing requirements and sharpening domain language against `CONTEXT.md`.
  - When the frontier is resolved, the assistant outputs a finalized plan and draft ADR with status `ready_for_approval`.
  - The UI renders an interactive **"Approve Plan & Build"** card in the chat timeline (or accepts text commands `/proceed` / `approve`).
- **Target Repository Scaffolding**:
  - Target applications created from `tanstack-start-template` (and existing repositories synced via `scripts/sync_target_repo_skills.py`) include `.agents/skills/` (Matt Pocock engineering skills), `CONTEXT.md`, `docs/agents/`, and `docs/adr/0001-tanstack-start-spa-architecture.md`.
  - **Template Provisioning Readiness & Polling**:
    - GitHub's template repository instantiation endpoint (`POST /repos/{template_org}/{template_repo}/generate`) replicates template files asynchronously on GitHub's backend.
    - To prevent Git database 409 errors ("Git Repository is empty"), `scaffold_target_repo` polls the default branch ref (`/git/ref/heads/{branch}`) and base commit (`/git/commits/{sha}`) with 1.0s ticks up to `timeout_secs` until **Template Provisioning Readiness** is established before creating the Git tree and commit.
    - If readiness is not established within the timeout window, `scaffold_target_repo` raises an explicit `RepoScaffoldingError` (HTTP 504) rather than attempting unrooted tree operations.
  - Upon user approval of a grilled plan, Factory Studio commits the approved ADR (e.g. `docs/adr/0002-<slug>.md`) and updated `CONTEXT.md` to GitHub on branch `factory/<feature>` before assembly line execution begins.
- **Assembly Line In-Sandbox Enforcement**:
  - **Pre-flight Guard (`preflight.ts`)**: Verifies that `docs/adr/` exists and contains at least one accepted ADR file in addition to `CONTEXT.md`.
  - **Planner Context (`lifecycle.ts` / `harness.ts`)**: Ingests `docs/adr/*.md` and injects their decisions and rationales into the Planner Agent's context bundle.
  - **Reviewer Audit (`harness.ts`)**: Updates `REVIEWER_SYSTEM_PROMPT` to explicitly audit the implementation diff against accepted ADRs under `standardsCompliance`, rejecting any changes that contradict recorded decisions.
