# 01: Decompose factory/ui/github.py

**What to build:**
Decompose the monolithic `factory/ui/github.py` (1,472 physical lines) into a cohesive directory package `factory/ui/github/` adhering to deep module principles:
- Create `factory/ui/github/`:
  - `_client.py`: Raw GitHub REST API HTTP calls, auth token resolution (`resolve_github_token`), caching, and error handling.
  - `_models.py`: Regex constants (`REPO_NAME_REGEX`), validation functions (`validate_github_repo_name`), and data structures.
  - `_issues.py`: Issue discovery, markdown issue parsing, issue status label manipulation, and comment posting.
  - `_prs.py`: Pull request discovery, delivery gate evaluation, diff extraction, and squash merge orchestration.
  - `_branches.py`: Branch inspection, git tree fetching, and template lineage cache.
  - `__init__.py`: Re-export all public functions, classes, and constants so existing imports (`from factory.ui.github import ...`) work seamlessly with zero caller changes.
- Invariant: Each internal file must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pytest tests/test_ui.py` to ensure all existing tests pass with zero modifications.

**Blocked by:** None (can start immediately)

**Status:** resolved
**Triage:** ready-for-agent

- [x] Create `factory/ui/github/` directory and internal sub-modules (`_client.py`, `_models.py`, `_issues.py`, `_prs.py`, `_branches.py`).
- [x] Move logic into respective sub-modules ensuring each file is $\le 500$ physical lines.
- [x] Populate `factory/ui/github/__init__.py` with all public re-exports matching the original module interface.
- [x] Remove legacy `factory/ui/github.py`.
- [x] Verify `pytest tests/test_ui.py` passes without test modifications.

## Comments

- Decomposed `factory/ui/github.py` into package directory `factory/ui/github/` with 5 internal submodules (`_client.py`, `_models.py`, `_issues.py`, `_prs.py`, `_branches.py`) and `__init__.py`.
- All newly created files strictly adhere to the line budget ($\le 500$ physical lines):
  - `__init__.py`: 90 lines
  - `_branches.py`: 425 lines
  - `_client.py`: 82 lines
  - `_issues.py`: 430 lines
  - `_models.py`: 54 lines
  - `_prs.py`: 221 lines
- All 182 tests in `tests/test_ui.py` pass with zero modifications.
