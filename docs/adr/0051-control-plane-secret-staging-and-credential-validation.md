# Control Plane Secret Staging and Credential Validation

**Status**: Accepted (Amends [ADR 0038](0038-centralized-org-credentials-and-in-repo-secrets.md), [ADR 0043](0043-sandbox-dot-directories-for-secrets-and-scripts.md), and [ADR 0049](0049-launch-fresh-sandboxes-from-web-control-plane.md))

We formalize dual-directory secret staging in the Hosted Sandbox Control Plane container image, introduce a centralized secret path resolution helper, add deploy-time asset validation, and provide actionable remediation errors when credentials are missing during fresh sandbox launches.

## Context

When launching fresh repository-backed sandboxes from the Hosted Sandbox Control Plane (`sandbox/function.py`) via the Web UI (`POST /api/sandboxes`), `sandbox.core.launch_sandbox()` executes within the control plane's Modal container. To provision child sandboxes with repository access, `launch_sandbox()` locates the Centralized Organization Credentials (`github-orgs.env`, per ADR 0038) and stages them into the child sandbox image via `image.add_local_file()`.

Previously, `sandbox/function.py` staged secrets using mutually exclusive branches:
```python
if (repo_root / ".secrets").is_dir():
    image = image.add_local_dir(str(repo_root / ".secrets"), "/root/.secrets")
elif (repo_root / "secrets").is_dir():
    image = image.add_local_dir(str(repo_root / "secrets"), "/root/.secrets")
```
Because target repository configurations maintain in-repo manifests (`.secrets/env.map`, `.secrets/studio.env`) in the root `.secrets/` directory, the `if` condition evaluated to `True`. As a result, the `elif` branch was skipped, omitting `secrets/` (including `secrets/github-orgs.env`, `secrets/cloudflare.env`, `secrets/opencode.env`, etc.) from the control plane image.

When an operator attempted to launch a repository-backed sandbox from the Web UI, `launch_sandbox()` raised:
```
FileNotFoundError: Organization credentials file not found: /root/secrets/github-orgs.env (expected .secrets/github-orgs.env or secrets/github-orgs.env).
```
which the Web API caught and returned as a generic `HTTP 404 Not Found` without remediation guidance. Furthermore, deploy-time commands (`modal deploy` / `modal serve`) did not validate the presence of required organization credentials.

## Decisions

1. **Dual Directory Staging in Control Plane Container Image (`sandbox/function.py`)**:
   - Unconditionally stage both `repo_root / "secrets"` to `/root/secrets` and `repo_root / ".secrets"` to `/root/.secrets` (if present) into the control plane image definition.
   - Maintains full repository layout parity inside the control plane container, ensuring all builder routines and secret references resolve cleanly.

2. **Centralized Secret Path Resolution (`shared.image.resolve_secret_path`)**:
   - Provide `resolve_secret_path(filename: str, repo_root: Path | None = None) -> Path | None` in `shared/image.py`.
   - Resolves secrets across `.secrets/` and `secrets/` directories under `repo_root`, `/root`, the codebase root, and the user's home directory.
   - Refactor `sandbox/core.py` and `shared/image.py` constants (`LOCAL_GITHUB_ORGS_SECRET`, `LOCAL_CLOUDFLARE_SECRET`, `LOCAL_OPENCODE_SECRET`, `LOCAL_ANTIGRAVITY_ENV`, etc.) to use this resolution order consistently.

3. **Deploy-Time Pre-flight Validation (`validate_deployment_credentials`)**:
   - Add pre-flight asset verification in `sandbox/function.py`.
   - Log a visible warning during deployment if `github-orgs.env` is missing, warning operators that repository sandbox provisioning will fail until provided.
   - Enforce a strict `RuntimeError` if `MODAL_ENFORCE_AUTH=1` or explicit enforcement is requested.

4. **Actionable Web API Error Responses (`sandbox/web.py` & `sandbox/function.py`)**:
   - Catch missing credential `FileNotFoundError` occurrences specifically in `POST /api/sandboxes` and `POST /launch`.
   - Return `HTTP 500 Internal Server Error` detailing that the control plane lacks required host credentials and instructing the operator to ensure `secrets/github-orgs.env` is present and redeploy via `modal deploy sandbox/function.py`.

5. **Regression & Image Contract Tests (`tests/test_sandbox/test_function.py`)**:
   - Add contract tests verifying that the control plane image stages both `/root/secrets` and `/root/.secrets`.
   - Add tests verifying `validate_deployment_credentials`, `resolve_secret_path`, and the 500 HTTP response mapping for missing credential files.

## Consequences

- Fresh repository sandboxes can be provisioned from the Hosted Control Plane Web UI without missing credential errors.
- Disparate secret lookup paths across `sandbox/core.py` and `shared/image.py` are unified into a single declarative resolver.
- Missing credentials are caught early at deployment time and return explicit remediation guidance instead of ambiguous HTTP 404 responses.
- All modified modules remain strictly within the universal <= 500 lines physical budget ratchet (ADR 0027 / AGENTS.md).
