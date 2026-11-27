# Ingress and Connectivity

Sandbox development ingress and VPS production ingress use different transports.

## Sandbox SSH

Startup runs OpenSSH on internal port 2222. Modal exposes an external host and port, which the launcher prints in its connection summary.

The launcher reads `sandboxes/shared/ssh-key.pub` and passes it as `SSH_AUTHORIZED_KEY` to startup. The client needs the matching private key, normally `~/.ssh/modal-sandbox`. To change the authorized key, update that public-key file on the launch host and redeploy a Hosted Sandbox Control Plane that uses it. See [SSH prerequisites](../getting-started/prerequisites.md#prepare-ssh-access).

A launch named `dev-box` creates an instance such as `dev-box-a1b2c3d4`. The CLI writes the generated instance alias to the launch machine's `~/.ssh/config`, unless `--no-ssh-config` is set. Hosted dashboard launches do not modify the browser user's local SSH configuration.

```ssh-config
Host dev-box-a1b2c3d4
    HostName <printed-modal-host>
    Port <printed-forwarded-port>
    User root
    IdentityFile ~/.ssh/modal-sandbox
    StrictHostKeyChecking no
    UserKnownHostsFile /dev/null
```

Use the actual printed values. You can also use `modal shell <sandbox-id>` with an authenticated Modal client.

## Sandbox application ingress with Cloudflare

Cloudflare support is enabled unless `--no-cloudflare` is passed, but startup requires `CLOUDFLARE_TUNNEL_TOKEN` to initialize the tunnel service. Without a token, startup logs that it is skipping initialization. It does not create a free `trycloudflare.com` quick tunnel.

Configure the tunnel's published application route to reach the sandbox web service on port 3000. `MODAL_SANDBOX_TUNNEL_DOMAIN` supplies the hostname shown in the connection summary; setting it does not create DNS records or configure routing.

The startup port watcher starts `cloudflared` when port 3000 is listening and stops it when that listener disappears. To use an application without public ingress, forward its port over SSH:

```bash
ssh -N -L 3000:127.0.0.1:3000 <printed-instance-alias>
```

## T3 Code, Metro, and desktop endpoints

| Option | Internal port | Transport |
| :--- | :--- | :--- |
| `--t3` | `3775`, or `--t3-port` | Modal HTTPS endpoint with a T3 pairing URL |
| `--react-native` | `8081`, or `--metro-port` | Modal HTTPS endpoint for Metro |
| `--xfce` | `3000`, or `--xfce-port` | noVNC web server; default port uses configured Cloudflare ingress, a custom port also receives a Modal HTTPS endpoint |

The T3 and Metro endpoints work independently of the Cloudflare application tunnel. OpenCode runs as an internal T3 provider; its retired standalone web server and port 4096 are no longer provisioned.

`--xfce` implies `--vm`. TigerVNC listens on `localhost:5901`, and noVNC/websockify bridges browser WebSocket traffic to it. Specify `--xfce-password` to enable VNC authentication; the default is passwordless auto-connect. See [runtimes](runtimes.md).

## VPS Host Ingress Proxy

Production Resource Plane and Hosted App HTTPS use Caddy in a separate Docker Compose stack at `/opt/caddy`, connected to `dbhost-network`. This is independent from sandbox Cloudflare tunnels.

- Resource Plane console and optional S3 hostnames use site files under `/opt/caddy/conf/sites/`.
- The apex of `APPS_BASE_DOMAIN` (`https://<APPS_BASE_DOMAIN>`) reverse-proxies via `apps-wildcard.caddy` without consuming Modal custom-domain slots: `modal-sandbox infra dashboard` deploys the Next.js Sandbox Web Dashboard container (`/opt/sandbox-dashboard`, `sandbox-dashboard-web:3000`) at apex while forwarding `/launch`, `/snapshot`, `/health`, and `/api/codex/profiles` to Modal (`SANDBOX_DASHBOARD_UPSTREAM` or Modal SDK discovery). When only `modal-sandbox infra caddy --wildcard` or `modal-sandbox infra deployer` has been run without an apex dashboard deploy, Caddy keeps those Modal CLI paths active at apex and returns `404` for browser paths.
- Hosted Apps and the standalone Dashboard Deployer (`modal-sandbox infra deployer`, running in `/opt/dashboard-deployer` as `dashboard-deployer-web:3000` on `https://deploy.<APPS_BASE_DOMAIN>`) use the wildcard certificate for `APPS_BASE_DOMAIN` and snippets under `/opt/caddy/conf/apps/`.
- The Cloudflare DNS-01 token for wildcard certificates is stored in `/opt/caddy/.env`, outside Central Config Store (`config/caddy/`) backups.

See [Resource Plane deployment](../guides/resource-plane-deployment.md) for bootstrap, backup, and restore, and [application deployment](../guides/applications.md) for wildcard DNS and app routes.
