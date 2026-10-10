# 02: TanStack Start Template Repository Provisioning

**What to build:** An application discovery and provisioning interface that lists available repositories under the canonical test organization and allows instantiating new project repositories from a canonical TanStack Start template repository using organization credentials, making new frontend project creation instantaneous and reliable.

**Blocked by:** 01: Dedicated Port 3010 and HTTP Basic Auth Security

**Status:** resolved

- [x] API endpoint returns the list of member repositories under the test organization with indicator for TanStack Start template compatibility.
- [x] API endpoint accepts a requested project name and creates a new repository in the test organization initialized from the canonical TanStack Start template repository.
- [x] Repository creation uses decrypted organization credentials in memory without persisting secrets to disk.
- [x] Validation prevents creating duplicate repository names or invalid GitHub repository slugs.
- [x] Automated tests verify repository listing and successful instantiation from the template using mocked GitHub API interactions.

## Answer

Resolved by implementing TanStack Start template repository provisioning and compatibility discovery:

1. **GitHub Repository Name & Slug Validation**:
   - Implemented `validate_github_repo_name(name: str)` in `factory/ui/github.py` enforcing GitHub repository naming rules (1-100 characters, alphanumeric ASCII start, only alphanumeric/hyphen/underscore/period, rejecting `.git`, `.`, `..`).
2. **TanStack Start Compatibility Discovery**:
   - Implemented `check_tanstack_start_compatibility(repo_item)` in `factory/ui/github.py` detecting TanStack Start scaffolding via template repository lineage (`tanstack-start-template`), repo topics (`tanstack-start`, `tanstack`), and repo descriptions.
   - Implemented `fetch_test_org_repos_detailed(token, org)` returning structured repository records with `is_tanstack_compatible` indicators.
   - Updated `GET /api/repos` and added dedicated `GET /api/studio/repos` in `factory/ui/app.py` returning member repositories with `is_tanstack_compatible` metadata while maintaining backward-compatible repository string lists.
3. **In-Memory Template Instantiation**:
   - Implemented `instantiate_repo_from_template(...)` in `factory/ui/github.py` ephemerally decrypting Test Organization credentials via host SOPS directly into memory without disk persistence.
   - Calls GitHub API `POST /repos/{template_org}/{template_repo}/generate` to instantiate new repositories in `software-factory-09-test` from `tanstack-start-template`.
   - Validates repository names, checks for existing duplicate repositories, and raises typed `RepoCreationError` mapped to HTTP status codes (400 Bad Request, 409 Conflict, 502 Bad Gateway).
4. **REST API Endpoints**:
   - Implemented `POST /api/repos` and `POST /api/studio/repos` accepting `CreateRepoRequest` (`name`, `project_name`, or `repo`, `description`, `private`), returning HTTP 201 Created with full repository metadata and `is_tanstack_compatible: True`.
5. **Automated Unit & Integration Testing**:
   - Added comprehensive tests in `tests/test_ui.py` covering slug validation, compatibility detection, mocked GitHub template generation, duplicate conflict rejection, missing token handling, and FastAPI endpoint contracts.

