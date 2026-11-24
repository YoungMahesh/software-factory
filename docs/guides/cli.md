# CLI Reference (`modal-sandbox`)

The `modal-sandbox` CLI is the primary developer interface for provisioning, managing, and snapshotting cloud sandboxes.

## Command Syntax

```bash
modal-sandbox [OPTIONS]
```

---

## Command Options

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-n, --name` | string | `None` | Instance and Modal App name (required for standalone runs). |
| `-r, --repo` | string | `None` | Target GitHub repository (`<owner>/<repo>` or shorthand `<repo>`). |
| `-b, --github-branch` | string | `main` | Git branch to clone and checkout. |
| `--full-clone` | flag | `False` | Perform a full Git clone (default is shallow clone with depth 50). |
| `--vm` | flag | `False` | Provision a Linux VM Sandbox with Docker daemon instead of standard container. |
| `--xfce` | flag | `False` | Provision an interactive XFCE 4 desktop and Google Chrome (automatically enforces `--vm`). |
| `--xfce-port` | integer | `3000` | Port for the noVNC websockify desktop bridge. |
| `--xfce-password` | string | `None` | Optional password for VNC session authentication (defaults to passwordless). |
| `--testing` | flag | `False` | Automatically prepend `test-` prefix to repository name in test organization. |
| `--t3` | flag | `False` | Launch T3 Code server with encrypted pairing URL and ASCII QR code. |
| `--browser` | flag | `False` | Pre-bake headless Google Chrome for Playwright and MCP tooling. |
| `--react-native` | flag | `False` | Install Android SDK/NDK, OpenJDK 17, Watchman, and Metro bundler tunnel. |
| `--modal` | flag | `False` | Install Modal SDK and client credentials inside sandbox virtualenv. |
| `--no-cloudflare` | flag | `False` | Disable default Cloudflare Tunnel ingress on port 3000. |
| `--no-ssh-config` | flag | `False` | Do not automatically append SSH connection details to `~/.ssh/config`. |
| `--sops` | flag | `False` | Retain Age private key in `~/.config/sops` for interactive debugging. |
| `--remote` | flag | `False` | Delegate sandbox execution to the hosted Modal control plane function. |
| `--snapshot <id>` | string | `None` | Capture a filesystem snapshot of a running sandbox ID. |
| `--from-snapshot <img-id>` | string | `None` | Launch a fresh sandbox from an existing filesystem snapshot image ID. |
| `--snapshot-ttl <days>` | integer | `30` | Snapshot retention period in days (used with `--snapshot`). |
| `--terminate` | flag | `False` | Terminate the sandbox immediately after taking a snapshot. |

---

## Common Usage Examples

### 1. Launch a Standalone Development Sandbox
```bash
modal-sandbox --name dev-box
```

### 2. Clone a Target Repository with AI Agent Stack
```bash
modal-sandbox -r my-service -b feature-auth --t3 --browser
```

### 3. Launch a Full Linux VM with Docker Daemon
```bash
modal-sandbox --name integration-box --vm
```

### 4. Launch an Interactive Cloud Desktop with Google Chrome
```bash
# Automatically launches XFCE 4 desktop, noVNC on port 3000, and Google Chrome in VM mode
modal-sandbox --name desktop-box --xfce

# Optional: specify a password to protect the remote VNC session
modal-sandbox --name secure-desktop --xfce --xfce-password "my-secret-pass"
```

### 5. Capture a Snapshot and Terminate
```bash
modal-sandbox --snapshot sb-abcdef123456 --terminate
```

### 6. Resume from Snapshot
```bash
modal-sandbox --from-snapshot im-9876543210 --name resumed-dev
```

---

## Central Environment Store CLI Utilities

### `push-repo-env`
Encrypts and commits repository secrets or Git authorship into the centralized `env-store` vault without leaving sensitive unencrypted keys in the workspace. Automatically creates and updates `<repo>/env.map` so destination mappings are immediately discoverable by `pull-repo-env` and git worktree propagation.

```bash
# Push default project application environment secrets (.env -> <repo>/default.env)
# Automatically creates/maintains default.env = .env in <repo>/env.map
push-repo-env [-r <repo>] [-o <org>] [-t <token>] [--recipient <key>]

# Push custom environment secrets (e.g. .env.local -> <repo>/local.env)
# NOTE: -d/--dest is REQUIRED whenever -e is not .env
# Automatically updates <repo>/env.map mapping local.env = .env.local
push-repo-env -e .env.local -d local.env [-r <repo>] [-o <org>] [-t <token>] [--recipient <key>]

# Push repository-specific Git authorship to <repo>/git.env
push-repo-env git --name "Jane Doe" --email "jane@example.com" [-r <repo>] [-o <org>] [-t <token>] [--recipient <key>]
```

#### `push-repo-env` Options

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `-r, --repo` | string | Origin remote | Target repository name. |
| `-o, --org` | string | `GH_ORG_NAME` | Target GitHub organization hosting `env-store`. |
| `-t, --token` | string | `GH_TOKEN` | GitHub Personal Access Token with repository write permissions. |
| `-e, --env` | path | `.env` | Path to local source environment file. |
| `-d, --dest` | string | `default.env` | Destination filename in vault. **Required if `-e` is not `.env`**. Automatically creates or updates `<repo>/env.map` in `env-store` mapping to the relative workspace path. |
| `--recipient` | string | Default key | Age public recipient key for SOPS encryption. |

#### `push-repo-env git` Options

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--name` | string | `GIT_AUTHOR_NAME` | Git author and committer name (or configured `git config user.name`). |
| `--email` | string | `GIT_AUTHOR_EMAIL` | Git author and committer email (or configured `git config user.email`). |
| `-r, --repo` | string | Origin remote | Target repository name. |
| `-o, --org` | string | `GH_ORG_NAME` | Target GitHub organization hosting `env-store`. |
| `-t, --token` | string | `GH_TOKEN` | GitHub Personal Access Token with repository write permissions. |
| `--recipient` | string | Default key | Age public recipient key for SOPS encryption. |

### `pull-repo-env`
Pulls and decrypts environment secrets from the `env-store` vault into the local directory (mode `0600`) and applies repository Git authorship locally to `.git/config`.

```bash
# Pull application secrets into .env and configure local Git authorship
pull-repo-env [-r <repo>] [-o <org>] [-d .env] [--optional]
```

### `ghclone`
Clones a target repository and automatically pulls decrypted secrets and Git authorship into the cloned directory via `pull-repo-env`.

```bash
ghclone my-service
```

---

## Database Provisioning CLI Utilities

### `create-db`
Provisions an isolated PostgreSQL database connection on the hosted `db-host` deployment, automatically resolves or creates the associated project, downloads and caches the TLS root CA certificate, and outputs or injects the connection URI into the local project `.env`.

```bash
# Provision or resolve database under current project (derived from Git repo name)
create-db <database_name>

# Explicitly target a project
create-db my-service-db -p custom-project

# Inject connection URI into local .env as DATABASE_URL
create-db my-service-db --write-env

# Inject into custom variable name in custom env file
create-db my-service-db --write-env --env-file .env.local --env-var ANALYTICS_DB_URL

# Inject and immediately encrypt into the central env-store vault
create-db my-service-db --write-env --push-vault

# Output raw JSON for automation and agent scripts
create-db my-service-db --json

# Strict mode: fail if database already exists
create-db my-service-db --fail-if-exists
```

#### `create-db` Options

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `name` | string | (required) | Target PostgreSQL database name to provision or resolve. |
| `-p, --project` | string | Git repo name / `default` | Project name on db-host. |
| `--domain` | string | `DB_HOST_DOMAIN` | Domain or URL of the db-host deployment. |
| `--token` | string | `DB_HOST_ADMIN_TOKEN` | Admin bearer token for MCP server authentication. |
| `--write-env` | flag | `False` | Inject or update connection URI in local `.env` file. |
| `--env-file` | path | `.env` | Path to target environment file for `--write-env`. |
| `--env-var` | string | `DATABASE_URL` | Variable name to write in environment file. |
| `--push-vault` | flag | `False` | Automatically push updated `.env` to central `env-store` vault via `push-repo-env`. |
| `--ca-path` | path | `~/.config/db-host/ca.crt` | Destination path for cached root CA certificate. |
| `--json` | flag | `False` | Emit raw credentials and connection details as JSON. |
| `-q, --quiet` | flag | `False` | Output only the PostgreSQL connection URI string. |
| `--fail-if-exists` | flag | `False` | Exit with error if database already exists instead of reusing existing connection. |

