# 01: Stage Centralized Organization Credentials in secrets/github-orgs.env

**What to build:**
Create and SOPS-encrypt a centralized organization credential store at `secrets/github-orgs.env` containing the `sFactory0` organization personal access token (`SFACTORY0_GH_TOKEN`), verified to decrypt cleanly with the workspace Age key. Completely retire and remove the obsolete `secrets_org/` directory from the workspace.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `secrets/github-orgs.env` is created with `SFACTORY0_GH_TOKEN` set to the `sFactory0` fine-grained PAT.
- [ ] `secrets/github-orgs.env` is encrypted using SOPS with the project Age public key.
- [ ] Decryption test verifies that `sops decrypt secrets/github-orgs.env` yields the valid plaintext token.
- [ ] The obsolete `secrets_org/` directory is deleted from version control and disk.
