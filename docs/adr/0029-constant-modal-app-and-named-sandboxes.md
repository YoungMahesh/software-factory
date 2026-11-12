# Constant Modal App and Named Sandboxes

Previously, `sandbox/main.py` created a new, ephemeral Modal App name for every sandbox launch (e.g. `<bare-repo>-<random-id>` or `test-<bare-repo>-<random-id>`), resulting in high App proliferation on Modal. We decided to transition to a constant App model where the Modal App remains fixed while individual Sandboxes are uniquely named (`modal.Sandbox.create(name=...)`) inside that App. For repository launches (`-s/--secret`), the App name is deterministic (`<bare-repo>`, or `test-<bare-repo>` when testing). For standalone launches without `--secret` and snapshot restores, `--name` defines the constant App name. Within the App, each sandbox is assigned a unique name (`<app-name>-<random-id>`) passed to `Sandbox.create()`.

## Considered Options

- **Single global App name (`software-factory`) for all sandboxes**: Launching every repository and standalone sandbox under a single monolithic Modal App. Rejected because grouping disparate repositories and test suites under a single App obscures workspace identity and complicates team quota or project attribution on the Modal dashboard.
- **Overriding App name with `--name` when `--secret` is passed**: Allowing both `--secret` and `--name` simultaneously. Rejected in favor of strict mutual exclusivity: `--name` is strictly for standalone launches without `--secret`, preventing ambiguous App naming collisions between repository secrets and custom CLI strings.
- **Reusing exact sandbox names without random suffixes**: Setting the sandbox name to strictly `<bare-repo>` and terminating existing instances on conflict. Rejected because concurrent sandboxes across multiple branches or developers would collide; using `<prefix><bare-repo>-<random-id>` provides unique, non-colliding named sandboxes within the constant App while surfacing explicit errors if collision occurs.

## Consequences

- The Modal App name is constant per project/repository (`<bare-repo>` or `test-<bare-repo>`) or per standalone application (`<name>`), looked up via `modal.App.lookup(app_name, create_if_missing=True)`.
- `--name` and `-s/--secret` are mutually exclusive in `sandbox/main.py`; passing both raises a CLI validation error.
- Sandboxes are named explicitly upon creation: `modal.Sandbox.create(app=app, name=sandbox_name, ...)`.
- If `modal.exception.AlreadyExistsError` is raised due to a name collision with an active sandbox, `sandbox/main.py` catches it, reports a diagnostic message, and exits with code 1 without mutating running containers.
- Container environment variable `APP_NAME` is set to `sandbox_name`, preserving isolation for Antigravity Remote Control instance registration (`agy remote-control start --name "$INSTANCE_NAME"`) and standalone workspace directory paths (`/root/<sandbox-name>`). `MODAL_APP_NAME` is exposed in `env` for the parent App identity.
- Terminal access information displays both the parent App name (`• App: <app-name>`) and the active Sandbox name (`• Sandbox: <sandbox-name>`), and formats the VS Code / SSH Config snippet host alias using the unique sandbox name (`Host <sandbox-name>`).
