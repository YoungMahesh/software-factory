# 04: Update Sandbox Runner and Startup for Centralized Org Tokens and In-Repo Secret Decryption

**What to build:**
Update `sandbox/main.py` to resolve target organization credentials from `secrets/github-orgs.env` and stage the credentials to the container without requiring local project secret directories. Update `shared/startup.sh` to extract the organization PAT, clone `sFactory0/<repo>`, check for `$TARGET_DIR/.secrets/env.map`, and decrypt all mapped `.env` files into place with `chmod 600`.

**Blocked by:** 01: Stage Centralized Organization Credentials in secrets/github-orgs.env, 02: Provision sFactory0/software-factory on GitHub with In-Repo .secrets/ Manifest

**Status:** completed

- [x] `sandbox/main.py` parses `secrets/github-orgs.env` to supply `GH_TOKEN` or stages the encrypted credential file into the container.
- [x] `sandbox/main.py` no longer looks for `secrets/<project>/fetch.env` or mounts `secrets_org/`.
- [x] `shared/startup.sh` extracts `GH_TOKEN` for the target repository organization.
- [x] `shared/startup.sh` clones `sFactory0/<repo>` over HTTPS using the organization token.
- [x] `shared/startup.sh` parses `$TARGET_DIR/.secrets/env.map` and decrypts mapped files to their destination paths with `chmod 600`.
- [x] Clean execution without errors when `.secrets/env.map` is absent.
- [x] Temporary staging secrets and `AGE_PRIVATE_KEY` are scrubbed before session handoff.
