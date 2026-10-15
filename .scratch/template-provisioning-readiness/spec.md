# Spec: Template Provisioning Readiness and Scaffolding Resilience

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

When a developer in Factory Studio creates a new target application from the canonical template (such as `expense-manager`), repository generation fails with an unexpected HTTP 409 error:

`Repository 'expense-manager' was created from template but failed to scaffold skills and ADRs: Failed to create Git tree (409): {"message":"Git Repository is empty.","documentation_url":"https://docs.github.com/rest/git/trees#create-a-tree","status":"409"}`

This failure occurs because GitHub's template instantiation API (`POST /repos/{template_org}/{template_repo}/generate`) creates the repository asynchronously. While GitHub returns `201 Created` immediately, background replication of template files and initial commits takes between one and three seconds to populate the Git database. Factory Studio previously invoked the scaffolding service immediately upon receiving the `201 Created` response. Because the Git database was not yet initialized at that exact moment, queries for the default branch reference failed to find an initial commit or base tree SHA. Scaffolding subsequently attempted to create a Git tree without a base tree reference, which GitHub rejects with `HTTP 409 Conflict: Git Repository is empty`.

Consequently:
1. Target application creation reports an error to the developer.
2. The created repository remains partially initialized on GitHub (containing the template files once replication completes, but missing Target Project Skills and Architectural Decision Records).
3. Any subsequent creation attempt with the same name fails with a 409 collision because the repository slug is already occupied.

## Solution

Implement an asynchronous readiness polling mechanism in the target repository scaffolding service to guarantee **Template Provisioning Readiness** before initiating Git tree operations:

1. **Template Provisioning Readiness Polling**:
   - Before attempting to create Git trees or commits, the scaffolding service polls GitHub's Git reference endpoint (`GET /git/ref/heads/{branch}`) and commit details endpoint (`GET /git/commits/{commit_sha}`).
   - Polling occurs with 1.0-second intervals up to the configured timeout budget (inherited from `timeout_secs`, defaulting to 20.0 seconds).
   - Once the default branch reference returns `200 OK` and a valid base tree SHA is resolved from the initial commit, Template Provisioning Readiness is established.

2. **Pre-Tree Invariant Assertion**:
   - If the timeout budget expires before Template Provisioning Readiness is established, the scaffolding service raises an explicit `RepoScaffoldingError` with HTTP status `504 Gateway Timeout` explaining that repository template replication did not complete within the timeout window.
   - The scaffolding service never attempts `POST /git/trees` without a verified base tree SHA on template-instantiated repositories, preventing cryptic 409 conflicts and ensuring existing template files are never accidentally orphaned.

3. **Domain Glossary and Architectural Alignment**:
   - Incorporate **Template Provisioning Readiness** into the canonical domain glossary in `CONTEXT.md`.
   - Amend Architectural Decision Record `0040-grill-with-docs-and-matt-pocock-skills-in-factory-studio.md` to document the asynchronous replication lifecycle and polling protocol.

## User Stories

1. As a developer in Factory Studio creating a new application, I want repository creation from the canonical template to succeed reliably, so that I can immediately begin specifying and generating features.
2. As a developer in Factory Studio, I want newly created repositories to be fully scaffolded with Target Project Skills and baseline ADRs, so that the assembly line pipeline satisfies all pre-flight guards.
3. As a developer creating a target application, I want the scaffolding routine to wait for GitHub's asynchronous template replication to complete, so that scaffolding requests do not race with repository initialization.
4. As a developer creating an application, I want the system to poll for repository readiness using an adaptable timeout budget, so that temporary GitHub queue latency does not cause premature creation failures.
5. As a developer whose repository initialization encounters a persistent GitHub outage or timeout, I want to receive an explicit 504 Gateway Timeout error explaining that template replication timed out, so that I understand why the operation failed rather than seeing a cryptic Git tree conflict.
6. As a developer creating an application, I want the scaffolding service to preserve the template's base Git tree SHA, so that scaffolding commits cleanly merge skills onto the template root without overwriting existing application files.
7. As an operator inspecting Factory Studio logs, I want scaffolding retries and readiness progression to be logged clearly, so that I can monitor repository provisioning latency.
8. As a test author running automated unit and integration tests, I want the scaffolding timeout and polling interval to be configurable, so that tests can assert retry and timeout behavior deterministically without unnecessary delays.
9. As an assembly line agent inspecting a newly scaffolded repository, I want `CONTEXT.md`, `docs/adr/`, and `.agents/skills/` to be present on the default branch immediately upon creation, so that requirement alignment and Pre-flight Guard passes without manual intervention.
10. As a developer inspecting repository creation errors, I want failed repository creation attempts to leave the repository intact on GitHub, so that the failure can be inspected and reported without unintended destructive actions.

## Implementation Decisions

- **Scaffolding Readiness Polling Loop**:
  The target repository scaffolding service will wrap initial reference resolution in a polling loop bounded by a monotonic deadline based on `timeout_secs`. Each iteration will query the Git branch reference endpoint. If the reference is not found or is unpopulated, the loop will sleep for 1.0 second and retry. Once the reference returns an object SHA, the service will fetch the commit details to acquire the root tree SHA.

- **Strict Pre-Tree Verification**:
  Tree creation payload generation will mandate the presence of `base_tree_sha`. If the polling deadline is reached without resolving both `commit_sha` and `base_tree_sha`, the service will raise a scaffolding error with status code 504 and an explicit timeout message, bypassing tree and commit endpoints.

- **Error Reporting Contract**:
  The repository template instantiation service will preserve its error handling boundary, surfacing scaffolding errors as repository creation errors with descriptive status codes and diagnostic messages.

- **Domain Model and Documentation Addendum**:
  The project domain documentation in `CONTEXT.md` and ADR 0040 will record `Template Provisioning Readiness` as the canonical requirement for transitioning from raw repository instantiation to skills scaffolding.

## Testing Decisions

- **Testing Principles**:
  Tests must exercise module behavior across external seams and assert observable outcomes (successful scaffolding metadata, retry progression, and explicit HTTP error exceptions) rather than inspecting internal loop variables.

- **Test Seam**:
  The primary test seam is the interface of the scaffolding module (`scaffold_target_repo`) against mocked HTTP client transport calls (`httpx.Client.get`, `httpx.Client.post`, `httpx.Client.patch`). An integration seam is verified at the repository instantiation module (`instantiate_repo_from_template`).

- **Tested Modules**:
  The target repository scaffolding module (`factory.ui.scaffold`) and the GitHub organization discovery module (`factory.ui.github`).

- **Prior Art**:
  Existing test suites in `tests/test_ui.py` (specifically `test_scaffold_target_repo_success` and `test_instantiate_repo_from_template_invokes_scaffolding`).

- **Required Test Scenarios**:
  1. *Transient Initialization Delay (Success with Polling)*: The branch reference returns 404 on the initial poll and 200 with valid commit and base tree SHAs on a subsequent poll. Assert that the scaffolding service retries, establishes readiness, and completes scaffolding successfully.
  2. *Initialization Timeout (Explicit 504 Failure)*: The branch reference returns 404 continuously until the deadline expires. Assert that `RepoScaffoldingError` is raised with status code 504 and that `POST /git/trees` is never invoked.
  3. *Immediate Readiness (Fast Path)*: The branch reference returns 200 on the first poll without delay, completing scaffolding in a single pass.
  4. *Integration with Repository Instantiation*: `instantiate_repo_from_template` propagates successful scaffolding metadata and handles 504 scaffolding timeouts by raising a structured creation error.

## Out of Scope

- Automatic deletion or rollback of GitHub repositories when scaffolding times out (repositories are retained as-is per design decision 3c).
- Manual re-scaffolding UI action in Factory Studio (can be addressed as a separate studio enhancement).
- Retroactive automatic mutation of existing unscaffolded repositories (e.g. `expense-manager` remains as-is per design decision 2c).

## Further Notes

- GitHub template generation latency is typically 1–3 seconds under normal network conditions. Setting the default timeout budget to 20.0 seconds provides a generous buffer against temporary GitHub API queue congestion while guaranteeing deterministic failure if a repository is genuinely unpopulated.
