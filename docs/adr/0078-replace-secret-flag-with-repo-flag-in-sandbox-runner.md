# Replace --secret Flag with --repo and Retire Legacy Secret Staging in Sandbox Runner

**Status**: Accepted (Amends [ADR 0016](0016-unified-sandbox-runner.md), [ADR 0018](0018-local-sops-encrypted-repository-secrets.md), [ADR 0031](0031-organization-credentials-and-canonical-test-organization.md), [ADR 0064](0064-optional-secret-and-standalone-sandbox-launch.md), and [ADR 0077](0077-centralized-org-credentials-and-in-repo-secrets.md))

## Context
Historically, `sandbox/main.py` used `-s` / `--secret` because each target repository maintained an individual directory on the host under `secrets/<repo>/fetch.env` (ADR 0018). With the acceptance of ADR 0077 (Centralized Organization Credentials and In-Repo Secrets Architecture), all repository authentication consolidated into a single SOPS-encrypted `secrets/github-orgs.env`, and project runtime secrets moved into `.secrets/env.map` inside target repositories. Consequently, the `--secret` argument in `sandbox/main.py` actually designated the GitHub repository being cloned, not a distinct secret file.

Furthermore, testing previously targeted a separate GitHub organization (`software-factory-09-test`, ADR 0031). Maintaining separate organizations created credential fragmentation and unnecessary access overhead.

## Decision
1. **Canonical `-r` / `--repo` CLI Flag**:
   - Replace `-s` / `--secret` with `-r` / `--repo` in `sandbox/cli.py` and `sandbox/main.py`.
   - Cleanly remove `-s` and `--secret`.
   - Update all CLI parser error and validation messages to reference `-r/--repo`.
2. **Unified Testing Under `sFactory0` with `test-` Prefix**:
   - Retire `software-factory-09-test` and `DEFAULT_TEST_ORG`.
   - Standardize default organization to `DEFAULT_ORG = "sFactory0"`.
   - When `--testing` is provided, automatically ensure the repository name carries the `test-` prefix under `sFactory0` (e.g. `sFactory0/test-<repo>`). If the user already provides `test-<repo>`, prevent duplicate prefixing.
3. **Purge Legacy Host Secrets Staging and Startup Fallbacks**:
   - Completely remove legacy `secrets/<repo>/fetch.env` and `secrets_org/` folder resolution from `sandbox/main.py`.
   - Stage `secrets/github-orgs.env` exclusively.
   - Purge legacy `/root/secrets/org/token` and `/root/secrets/repo/fetch.env` fallback branches from `shared/startup.sh`.

## Consequences
- CLI semantics directly describe the action being performed (cloning `--repo`).
- Host repository secret sprawl and legacy fallbacks are eliminated.
- Test workflows use unified organization credentials with predictable, isolated `test-` repository namespaces under `sFactory0`.
