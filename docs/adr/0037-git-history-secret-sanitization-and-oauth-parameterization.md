# Git History Secret Sanitization and OAuth Parameterization

**Status**: Accepted

## Context
GitHub Push Protection rejected pushes to the remote repository due to secrets found in commit history:
1. Google OAuth Client ID and Client Secret embedded in `scripts/setup.sh` and `shared/startup.sh`.
2. A sample Docker Personal Access Token (`dckr_pat_...`) embedded in Modal documentation references (`.agents/skills/modal/references/guide/existing-images.md`).

## Decision
1. **Dynamic Parameterization**: Replace hardcoded Google OAuth client credentials in active startup and setup scripts with environment variables (`ANTIGRAVITY_CLIENT_ID` / `GOOGLE_CLIENT_ID`, `ANTIGRAVITY_CLIENT_SECRET` / `GOOGLE_CLIENT_SECRET`) falling back to non-sensitive placeholders.
2. **Docs Sanitization**: Replace the Docker PAT example with a placeholder string that does not trigger push protection patterns.
3. **History Rewriting**: Use `git-filter-repo` text replacements across all branches to purge the exact secret strings from historical commit trees without altering the commit topology or authorship.
4. **Staged Push Validation**: Push the sanitized history to a clean tracking branch (`main-clean`) on the remote to verify that GitHub Push Protection passes before replacing remote `main`.
5. **Encrypted Tooling Secrets**: Store Google OAuth credentials (`ANTIGRAVITY_CLIENT_ID` and `ANTIGRAVITY_CLIENT_SECRET`) SOPS-encrypted in `secrets/antigravity.env`. Startup and setup scripts decrypt the variables in memory to provision ACP tokens at boot without exposing plaintext credentials in Modal secrets (`share0`) or git commits, scrubbing the staged file immediately after decryption.
