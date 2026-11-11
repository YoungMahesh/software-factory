# Hosted Control Plane & Web Dashboard

Modal Sandboxes includes a serverless web dashboard and REST API implemented using FastAPI and hosted directly on Modal (`sandbox/function.py`).

## Deploying the Control Plane

### 1. Requirements in `.env`
Set credentials in your local `.env`:

```env
WEB_UI_USERNAME=admin
WEB_UI_PASSWORD=secure-password-here
```

### 2. Deploy to Modal Cloud
Deploy as a persistent, serverless FastAPI endpoint:

```bash
modal deploy sandbox/function.py
```

Modal will output the public URL of your control plane function (e.g., `https://<org>--modal-sandboxes-web.modal.run`).

### 3. Local Development (Serve Mode)
Run live with hot-reloading for local testing:

```bash
modal serve sandbox/function.py
```

---

## Web Dashboard (`GET /`)

Access `GET /` in any modern web browser. You will be prompted for HTTP Basic Authentication (`WEB_UI_USERNAME` and `WEB_UI_PASSWORD`).

Key Dashboard features:
- **Active Sandbox Discovery**: View all running and paused sandboxes across all registered Modal apps (see [ADR 0086](../adr/0086-cross-app-sandbox-discovery-in-control-plane-web-ui.md)).
- **One-Click Launch**: Launch fresh standalone sandboxes or clone target GitHub repositories directly from the web interface.
- **Snapshot Registry**: Inspect captured filesystem snapshots and launch new sandboxes from existing snapshot images.
- **Instance Management**: Terminate running sandboxes and view connection parameters.

---

## REST API Reference

The control plane exposes programmatic REST endpoints for automation:

### Authentication
- All control plane endpoints (both browser UI routes under `/`, `/api/` and headless automation endpoints `/launch`, `/snapshot`) use standard HTTP Basic Authentication with `WEB_UI_USERNAME` and `WEB_UI_PASSWORD`:
  `Authorization: Basic <base64(WEB_UI_USERNAME:WEB_UI_PASSWORD)>`
- CLI commands running with `--remote` automatically authenticate using `WEB_UI_USERNAME` and `WEB_UI_PASSWORD`.

### Key Endpoints

| Method | Endpoint | Auth | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Basic | Interactive web management dashboard. |
| `GET` | `/health` | None | Service liveness probe. |
| `GET` | `/api/sandboxes` | Basic | List active sandboxes across Modal applications. |
| `POST` | `/api/sandboxes` | Basic | Launch a new sandbox with custom flags and repository targets. |
| `POST` | `/api/sandboxes/{id}/terminate` | Basic | Terminate an active sandbox. |
| `POST` | `/api/sandboxes/{id}/snapshot` | Basic | Capture a filesystem snapshot of a sandbox. |
| `POST` | `/api/snapshots/{image_id}/launch` | Basic | Launch a fresh sandbox from a snapshot image. |
| `POST` | `/launch` | Basic | Headless sandbox provisioning endpoint. |
| `POST` | `/snapshot` | Basic | Headless snapshot capture endpoint. |
