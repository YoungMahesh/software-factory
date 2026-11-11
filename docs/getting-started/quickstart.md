# Quickstart (Zero-Config in 60s)

Launch a clean standalone cloud development sandbox with zero external configuration beyond the standard Modal CLI.

## Launching Your First Sandbox

Run the `modal-sandbox` CLI with a chosen sandbox name:

```bash
modal-sandbox --name my-first-sandbox
```

Upon execution, the runner performs the following steps automatically:

1. **Builds / Caches Image Layers**: Reuses prebaked Ubuntu images with Python 3.11, OpenSSH, and developer utilities.
2. **Generates SSH Keys**: Configures an OpenSSH server on port 2222 inside the container and injects your connection profile into `~/.ssh/config`.
3. **Starts Ingress Tunnel**: Establishes a Cloudflare Tunnel forwarding port 3000 to the web.
4. **Initializes Workspace**: Sets up `/root/my-first-sandbox` with an empty Git repository and default Python virtual environment.

Output resembles:

```text
Provisioning Modal Sandbox: my-first-sandbox...
SSH configured: ssh my-first-sandbox
Web Ingress: https://<tunnel-id>.trycloudflare.com -> port 3000
Sandbox running (ID: sb-xxxxxxxx)
```

---

## Connecting via SSH

You can connect directly using the alias written to `~/.ssh/config`:

```bash
ssh my-first-sandbox
```

Or connect via the Modal CLI's native interactive shell:

```bash
modal shell <sandbox-id>
```

---

## Testing Web Ingress

Every sandbox includes a web ingress tunnel routed to container port `3000`. Test it by starting a simple HTTP server inside the sandbox:

```bash
ssh my-first-sandbox "python3 -m http.server 3000 --directory /root/my-first-sandbox"
```

Open the printed `trycloudflare.com` URL in your browser to view your sandbox files served live over HTTPS.

---

## Next Steps

- Learn about [Dual Execution Runtimes](../architecture/runtimes.md) (Standard Container vs Linux VM).
- Explore [Capturing and Resuming Snapshots](../architecture/snapshots.md).
- View all available options in the [CLI Reference](../guides/cli.md).
