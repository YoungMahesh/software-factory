# Hosted Control Plane & Web Dashboard

Modal Sandboxes includes a serverless web dashboard and REST API implemented using FastAPI and hosted directly on Modal (`sandbox/function.py`).

## Deploying the Control Plane

### 1. Requirements in `.env`
Set credentials in your local `.env`:

```env
WEB_UI_USERNAME=admin
WEB_UI_PASSWORD=secure-password-here
MODAL_SANDBOX_AUTH_TOKEN=your-bearer-token
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
- Endpoints under `/api/` accept HTTP Basic Authentication.
- Headless automation endpoints (`/launch`, `/snapshot`) accept HTTP Bearer token authentication via header: `Authorization: Bearer <MODAL_SANDBOX_AUTH_TOKEN>`.

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
| `POST` | `/launch` | Bearer | Headless sandbox provisioning endpoint. |
| `POST` | `/snapshot` | Bearer | Headless snapshot capture endpoint. |
