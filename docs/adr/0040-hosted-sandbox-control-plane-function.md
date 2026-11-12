# Hosted Sandbox Control Plane Function

**Status**: Accepted (Amends [ADR 0005](0008-unified-base-image-for-standard-and-vm-sandboxes.md), [ADR 0005](0026-production-file-line-budget-and-ratchet.md), [ADR 0003](0029-constant-modal-app-and-named-sandboxes.md), and [ADR 0063](0063-replace-secret-flag-with-repo-flag-in-sandbox-runner.md))

## Context

Historically, Modal sandboxes in this repository were provisioned strictly from the local developer CLI (`sandbox/main.py`). The local host had to maintain Python 3, the Modal SDK, active Modal credentials (`~/.modal.toml`), and local network connectivity while executing sandbox creation, polling tunnels, and running post-launch pairing scripts.

Hosting the sandbox launcher as a deployed Modal cloud function (`sandbox/function.py`) provides several key advantages:
1. **Zero-Setup Triggering**: Remote callers (webhooks, GitHub Actions, Slack bots, curl, external services) can provision sandboxes via an HTTP POST request without requiring Python or the Modal SDK installed locally.
2. **Synchronous Cloud Control Plane**: Modal sandboxes, tunnel resolution, and T3/OpenCode post-launch pairing scripts execute directly inside Modal's high-speed cloud infrastructure rather than relying on local machine networks.
3. **Decoupled Architecture & Shared Core**: To maintain the 500 physical line budget per file (ADR 0005), shared sandbox provisioning and lifecycle execution logic must be factored into a reusable module (`sandbox/core.py`) used by both the local CLI and the cloud function.

## Considered Options

- **Single Webhook Function with Internal Modal Functions (`@modal.web_endpoint`)**: Expose only a single raw webhook function accepting ad-hoc query or form parameters. Rejected because it complicates multi-action operations (such as filesystem snapshotting) and lacks clean OpenAPI schema validation.
- **Asynchronous Job / Queue Pattern**: Return a job ID immediately and require callers to poll a `/status` endpoint until the sandbox is ready. Rejected because sandbox boot and tunnel resolution complete in 10–25 seconds; a synchronous HTTP endpoint with a 120–180 second timeout is much simpler for clients (like `curl` or automated CI runners) to consume in a single invocation.
- **FastAPI ASGI Application on Modal (`@modal.asgi_app()`)**: Deploy a lightweight FastAPI app named `sandbox-control-plane` via `modal deploy sandbox/function.py`. Accepted because it provides clear route separation (`POST /launch`, `POST /snapshot`, `GET /health`), declarative Pydantic request/response validation, bearer token authentication (`MODAL_SANDBOX_AUTH_TOKEN` in `share0`), and full client interoperability with both HTTP clients and the local CLI via `--remote`.

## Decisions

1. **Control Plane Modal App (`sandbox/function.py`)**:
   - Deployed as `sandbox-control-plane` using `modal deploy sandbox/function.py`.
   - Packages repository dependencies (`shared`, `sandbox`, `shared/startup.sh`, `shared/ssh-key.pub`, and `secrets/github-orgs.env`) into a cached container image.
   - Exposes a FastAPI application with `/health`, `/launch`, and `/snapshot` routes protected by Bearer token authentication against `MODAL_SANDBOX_AUTH_TOKEN` (permissive if unset).
   - Strict SSH Key Binding: Uses the repository's tracked public key (`shared/ssh-key.pub`); does not allow arbitrary SSH key injection over HTTP.

2. **Core Provisioning Extraction (`sandbox/core.py`)**:
   - Extracts `launch_sandbox`, `validate_launch_request`, `capture_snapshot_core`, and Pydantic schemas (`LaunchRequest`, `LaunchResponse`, `SnapshotRequest`, `SnapshotResponse`) into `sandbox/core.py`.
   - Ensures both `sandbox/main.py` and `sandbox/function.py` stay well below the 500-line budget limit.

3. **CLI Remote-Mode Integration (`sandbox/main.py` & `sandbox/cli.py`)**:
   - Adds `--remote` and `--endpoint-url` (falling back to `MODAL_SANDBOX_ENDPOINT_URL`) to `sandbox/cli.py`.
   - In remote mode, `sandbox/main.py` delegates JSON payload dispatch over HTTP and prints the formatted terminal connection summary and QR code locally.

## Consequences

- The control plane can be deployed to Modal with `modal deploy sandbox/function.py`.
- External systems can launch sandboxes using simple `curl` commands with `Authorization: Bearer <token>`.
- Developers can use `python3 sandbox/main.py --remote` to provision sandboxes in the cloud without local Modal SDK execution overhead.
- All code files strictly adhere to the universal 500 physical line budget.
