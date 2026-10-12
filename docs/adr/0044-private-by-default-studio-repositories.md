# Private-by-Default Repository Policy in Factory Studio

**Status**: Accepted

To protect application code, prevent accidental public exposure of generated applications, and ensure security-by-default across target projects developed in the Test Organization (`software-factory-09-test`), we decided to implement the **Private-by-Default Repository Policy** across Factory Studio and backend repository creation endpoints, while providing an opt-out visibility toggle in the user interface.

## Considered Options

- **Retaining Public-by-Default Creation (Prior Behavior)**: Generating repositories from templates with `private: false` unless explicitly passed as private in API requests. Rejected because developers frequently generate prototypes without configuring visibility, leading to unintentional public disclosure of proprietary code and project structures.
- **Strictly Mandatory Private Repositories without User Override**: Enforcing that all newly instantiated repositories are unconditionally private without any UI control or configuration to make them public. Rejected because developers occasionally need to scaffold open-source or public showcase applications directly from Factory Studio.
- **Private-by-Default with Opt-Out UI Toggle and Metadata Indicators**:
  - Updating backend Pydantic schemas (`CreateRepoRequest.private = True`) and GitHub template generation (`instantiate_repo_from_template(..., private=True)`) to default to private repositories.
  - Adding an explicit "Private repository" checkbox toggle in Factory Studio's `NewAppModal` (defaulting to checked) with clear organization access subtitle guidance.
  - Exposing repository visibility (`private: bool`) in organization repository listings (`fetch_test_org_repos_detailed`) and rendering subtle lock indicators (`🔒` / Private badge) in Factory Studio and Testing Console repository selectors.
  Accepted.

## Consequences

- The canonical term **Private-by-Default Repository Policy** is recorded in `CONTEXT.md`.
- **Backend API & Schema**:
  - `CreateRepoRequest` in `factory/ui/app.py` defines `private: bool = Field(True, description="Whether created repository is private")`.
  - `instantiate_repo_from_template` in `factory/ui/github.py` defines parameter default `private: bool = True`.
  - `fetch_test_org_repos_detailed` and fallback listings in `factory/ui/github.py` extract and return `"private": bool(r.get("private", False))`.
- **Frontend UI & User Experience**:
  - `NewAppModal` (`factory/ui/frontend/src/components/NewAppModal.tsx`) introduces a checkbox toggle for repository visibility, initialized to checked (`isPrivate: true`), and submits the selected preference to `onCreate`.
  - `StudioView` and `TestingConsoleView` display visual lock indicators (`🔒`) in repository dropdown options and a dedicated "Private" badge when an active private repository is selected.
  - `Repo` interface in `factory/ui/frontend/src/types.ts` is updated to include `private?: boolean`.
- **Scope & Non-Interference**:
  - Policy applies strictly to newly created repositories going forward; existing repositories in `software-factory-09-test` are not mutated.
  - Full end-to-end compatibility is maintained with organization credentials (`secrets_org/software-factory-09-test/token`) which hold `repository_creation: read-write` fine-grained permissions.
