# 02: Provision sFactory0/software-factory on GitHub with In-Repo .secrets/ Manifest

**What to build:**
Create private repository `sFactory0/software-factory` on GitHub using the organization PAT. Commit an in-repo `.secrets/` directory containing `env.map` (`studio.env=.env`) and the SOPS-encrypted `studio.env` payload, push the codebase to `sFactory0/software-factory`, and remove the local `secrets/software-factory/` staging directory from the host.

**Blocked by:** 01: Stage Centralized Organization Credentials in secrets/github-orgs.env

**Status:** completed

- [x] Private repository `sFactory0/software-factory` is created on GitHub under the `sFactory0` organization.
- [x] Directory `.secrets/` is established inside `software-factory` containing `env.map` pointing `studio.env=.env`.
- [x] The encrypted `.secrets/studio.env` file is placed and verified to decrypt with `AGE_PRIVATE_KEY`.
- [x] The repository is pushed to `sFactory0/software-factory` main branch.
- [x] The local directory `secrets/software-factory/` is removed from the host.
