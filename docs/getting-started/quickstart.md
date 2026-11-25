# Launch Your First Sandbox

Complete [setup](prerequisites.md) first, including Modal authentication. SSH access also requires the private key matching the launch host's `sandboxes/shared/ssh-key.pub`.

## Launch and connect

```bash
modal-sandbox --name dev-box --no-cloudflare
```

The launcher creates a sandbox instance with a generated suffix, such as `dev-box-a1b2c3d4`, under the Modal App `dev-box`. Startup initializes an empty Git workspace at `/root/dev-box-a1b2c3d4` and starts SSH on internal port 2222. Python virtualenv setup is enabled separately by `--modal`.

Use the instance alias printed in the connection summary:

```bash
# Replace this sample alias with the one from your launch output.
ssh dev-box-a1b2c3d4

# Or use the sandbox ID with your authenticated Modal client.
modal shell <sandbox-id>
```

The CLI registers the generated SSH alias in `~/.ssh/config` unless `--no-ssh-config` is set. The hosted dashboard displays connection details; launching through the dashboard does not edit your laptop's SSH configuration.

## Run a web server

Start a server inside the sandbox, then forward it through SSH from your local machine:

```bash
ssh dev-box-a1b2c3d4 'python3 -m http.server 3000 --directory /root'
```

In a second local terminal:

```bash
ssh -N -L 3000:127.0.0.1:3000 dev-box-a1b2c3d4
```

Open `http://localhost:3000`. For public HTTPS, configure a Cloudflare tunnel token and route, then launch without `--no-cloudflare`; see [ingress](../architecture/ingress.md). Startup does not create a credential-free quick tunnel.

## Launch a repository with T3 Code

With GitHub access configured:

```bash
modal-sandbox --repo my-org/my-repo --t3 --no-cloudflare
```

T3 Code uses its own Modal HTTPS endpoint and pairing URL. `--t3` also enables browser tooling; provider authentication is described in [AI tooling](../guides/ai-tooling.md).

## Stop the sandbox

Use its dashboard termination action, or run the management utility from the factory checkout:

```bash
python sandboxes/scripts/manage_sandboxes.py --all-apps --terminate <sandbox-id>
```

Continue with [runtimes](../architecture/runtimes.md), [snapshots](../architecture/snapshots.md), [application scaffolding](../guides/applications.md), or the [CLI reference](../guides/cli.md).
