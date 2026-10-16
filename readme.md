# Software Factory

Automated software delivery pipeline executing multi-agent assembly lines in ephemeral Modal Sandboxes.

---

## 1. Setup

```bash
pip install -r requirements.txt
bash scripts/setup.sh --modal --agy --opencode
```

Decrypts credentials via local SOPS into standard user paths (`~/.modal.toml`, `~/.gemini/antigravity-cli/`, `~/.config/opencode/`).

For frontend development, Node.js 24 and pnpm 10 are required:
```bash
pnpm --dir factory/ui/frontend install
```

---

## 2. Web Workspace (Factory Studio & Console)

The web workspace is a compiled Vite React SPA statically served by FastAPI at `/` (per ADR 0036).

### Launch Server (Compiled React SPA)

```bash
python factory/run.py --ui  # Default: http://127.0.0.1:3010
```

- **Factory Studio**: Split-pane prompt interface with live preview (`https://3000.mahesh0.dev`) for frontend applications.
- **Factory Testing Console**: Real-time assembly line orchestration, SSE log streaming, and milestone stepper for `software-factory-09-test`.
- **Auth**: Basic HTTP Auth (`admin:admin` default; configure via `FACTORY_AUTH_USER` and `FACTORY_AUTH_PASS`).
- **Flags**: `--host <ip>` (default `127.0.0.1`), `--port <port>` (default `3010`), `--open` (auto-open browser).

### Frontend Development (Vite HMR)

For active React UI development with Hot Module Replacement (HMR):

```bash
# 1. Start backend API server on port 3010:
python factory/run.py --ui

# 2. Start Vite React dev server on port 5173 (proxies /api to port 3010):
pnpm --dir factory/ui/frontend dev

# 3. Compile production bundle into factory/ui/static/dist/:
pnpm --dir factory/ui/frontend build

# 4. Run Vitest test suite:
pnpm --dir factory/ui/frontend test
```

---

## 3. CLI Dispatcher

```bash
# Autonomous batch on Test Organization:
python factory/run.py -p <repo> -f <feature> --testing

# Single ticket execution on Test Organization:
python factory/run.py -p <repo> -f <feature> -i 01 --testing

# Production repository (configured under secrets/<project>/):
python factory/run.py -p <project> -f <feature>
```

| Flag | Description | Default |
| :--- | :--- | :--- |
| `-p, --project` | Target repository name | *Required* |
| `-f, --feature` | Target feature slug (`.scratch/<feature>/`) | *Required* (or `-i`) |
| `-i, --issue` | Specific ticket ID (e.g. `01`). Omit for full batch | Full batch |
| `--testing` | Target repositories under Test Organization `software-factory-09-test` | `False` |
| `--vm` | Provision a VM Sandbox with Docker support instead of a Standard Sandbox | `False` |
| `--memory <GB>` | RAM allocation in GB (for VM sandboxes; 2× swap) | `1` |
| `-m, --model` | LLM selection (`deepseek-v4.1-flash` or `mimo-v2.6-flash`) | `deepseek-v4.1-flash` |
| `--dev` | Maintain in-sandbox dev preview keep-alive server on port 3000 | `False` |
| `--tracker` | Issue tracker backend (`github` or `local`) | Auto-detected |
| `--ui` | Launch web interface on `--host` and `--port` | `False` |

---

## 4. Modal Sandboxes

Standalone cloud development sandboxes with SSH and Cloudflare Tunnel ingress:

```bash
python sandbox/main.py -s <secret-name> [--vm] [--opencode] [--agy] [--modal]
```

See [`sandbox/readme.md`](sandbox/readme.md) for secrets configuration (`share0`, `fetch.env`, `env.map`) and runner options.

---

## 5. Prompt Templates

Externalized system prompt templates used across Factory Studio and the Assembly Line:

- (grilling_assistant.md)[factory/ui/grill/prompts/grilling_assistant.md]
- (planner_system.md)[sandbox/factory/harness/prompts/planner_system.md]
- (coder_system.md)[sandbox/factory/harness/prompts/coder_system.md]
- (reviewer_system.md)[sandbox/factory/harness/prompts/reviewer_system.md]

