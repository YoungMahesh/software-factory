# 03: Migrate repo-horizon, intrifund, and neon to sFactory0 with In-Repo .secrets/

**What to build:**
Clone `repo-horizon`, `intrifund`, and `neon` from their current remotes (`anveshak71`), create corresponding private repositories under `sFactory0` on GitHub, populate their respective `.secrets/env.map` and SOPS-encrypted `.env` files, push to `sFactory0`, and eliminate `secrets/repo-horizon/`, `secrets/intrifund/`, and `secrets/neon/` from the host.

**Blocked by:** 01: Stage Centralized Organization Credentials in secrets/github-orgs.env

**Status:** ready-for-agent

- [ ] Private repositories `sFactory0/repo-horizon`, `sFactory0/intrifund`, and `sFactory0/neon` are created on GitHub.
- [ ] `repo-horizon` contains `.secrets/env.map` mapping `web.env` and `mobile.env` to their package destinations, with corresponding SOPS-encrypted files in `.secrets/`.
- [ ] `intrifund` contains `.secrets/env.map` mapping `intrifund-dev.env`, `intrifund-preview.env`, `mock-intriemp-dev.env`, and `call-api.env` to their respective subproject paths, with encrypted files in `.secrets/`.
- [ ] `neon` is migrated to `sFactory0/neon`.
- [ ] Host-side directories `secrets/repo-horizon/`, `secrets/intrifund/`, and `secrets/neon/` are deleted.
