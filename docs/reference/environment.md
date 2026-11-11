# Environment Variables Reference

Modal Sandboxes uses a unified `.env` file for local development and control plane operations.

## Configuration Variables

### 1. Control Plane & Dashboard Authentication
- `WEB_UI_USERNAME`: Username for HTTP Basic Authentication on the web dashboard and REST API routes (`POST /launch`, `POST /snapshot`) (default: `admin`).
- `WEB_UI_PASSWORD`: Password for HTTP Basic Authentication on the web dashboard and REST API routes (`POST /launch`, `POST /snapshot`).

### 2. Modal Cloud Authentication
- `MODAL_TOKENS`: JSON array string containing multi-account Modal profile objects with credentials (`token_id`, `token_secret`, optional `active`).

### 3. Source Control & GitHub
- `GH_TOKEN`: GitHub Personal Access Token with repository read/clone permissions.
- `GH_ORG_NAME`: Default GitHub organization name (e.g., `sFactory0`). When passing shorthand `-r <repo>`, the runner clones `https://github.com/${GH_ORG_NAME}/${repo}`.

### 4. Remote Ingress & SSH
- `CLOUDFLARE_TUNNEL_TOKEN`: Cloudflare Tunnel credential token for custom ingress domains.
- `MODAL_SANDBOX_TUNNEL_DOMAIN`: Optional custom hostname display format (e.g. `3000.yourdomain.com`).
- `SSH_AUTHORIZED_KEY`: Optional explicit SSH public key string to authorize in addition to `shared/ssh-key.pub`.

### 5. AI Tooling Providers
- `OPENCODE_GO_API_KEY`: API key for OpenCode Go provider.
- `ANTIGRAVITY_CLIENT_ID`: OAuth client ID for Google Antigravity.
- `ANTIGRAVITY_CLIENT_SECRET`: OAuth client secret for Google Antigravity.
- `ANTIGRAVITY_TOKENS`: JSON array string containing Antigravity user profile credentials.

### 6. Encryption & SOPS
- `AGE_PRIVATE_KEY`: Age private key (`AGE-SECRET-KEY-...`) used by SOPS to decrypt repository environment secrets.

### 7. Software Factory Provenance (In-Sandbox & Control Plane)
- `SOFTWARE_FACTORY_COMMIT`: Full 40-character Git commit SHA of the `software-factory` checkout from which the sandbox was created.
- `SOFTWARE_FACTORY_COMMIT_SHORT`: 7-character short commit SHA.
- `SOFTWARE_FACTORY_REF`: Git branch or tag name of the `software-factory` checkout (e.g. `main`).
- `SOFTWARE_FACTORY_DIRTY`: Boolean indicator (`"1"` or `"0"`) signaling whether the host checkout had uncommitted modifications at the time of sandbox creation.
