# Issue 01: GitHub Discovery Client for Test Organization

Status: resolved

## Objective
Implement `factory/ui/github.py` to securely decrypt `secrets_org/software-factory-09-test/token` into memory using host `sops` and query the GitHub REST API to list repositories under the canonical test organization, and query the Git Tree API for a given repository to discover `.scratch/<feature>/` directories and ticket files (`issues/<NN>-*.md`).

## Acceptance Criteria
- Token is decrypted ephemerally into memory; never written to plaintext files or returned in API responses.
- Queries `GET /orgs/software-factory-09-test/repos` and returns repository names.
- Queries `GET /repos/software-factory-09-test/{repo}/git/trees/main?recursive=1` and parses `.scratch/` feature slugs and issue paths.
- Gracefully handles offline or missing token scenarios by falling back to known fixtures (`test1`, `test2`, `test3`).
