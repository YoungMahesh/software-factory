# Isolated Virtual Environments for Python Tooling

Python projects require runtime dependency isolation to avoid polluting system site-packages, breaking Debian package manager dependencies, or requiring manual `python3 -m venv .venv` and `source .venv/bin/activate` upon connecting to a sandbox. We decided to automatically provision an isolated virtual environment (`.venv`) at the repository root upon clone when `--python` is passed, install dependencies from `requirements.txt` directly into `.venv`, and configure automatic activation across developer login and interactive shells.

## Considered Options

- **Global pip install with break-system-packages**: Install Python packages globally into the system Python site-packages with `break-system-packages = true`. Rejected because it creates friction when developer projects expect an active `.venv`, leads to missing virtual environments upon SSH connection, and risks colliding with Debian system packages.
- **Manual venv creation by developer**: Expect developers to run `python3 -m venv .venv` and `pip install -r requirements.txt` manually after SSH or modal shell login. Rejected because it adds manual onboarding friction on every new sandbox launch.
- **Automated .venv provisioning and shell activation**: Provision `$TARGET_DIR/.venv` immediately after repository clone in `startup.sh`, install `requirements.txt` into `.venv`, configure auto-activation in `~/.bashrc` and `/etc/profile.d/`, and record `VIRTUAL_ENV` in `/etc/environment`. Accepted because developers connect into an immediately active, isolated virtual environment with all required binaries (like `modal`) available in `PATH`.

## Consequences

- Sandboxes launched with `--python` have `$TARGET_DIR/.venv` pre-created and pre-populated from `requirements.txt`.
- Developers connecting via SSH, VS Code Remote SSH, or `modal shell` immediately have their shell activated in `.venv` without manual intervention.
- The repository declares its dependencies in `requirements.txt` (e.g. `modal>=1.6.1`), enabling standard Python dependency management workflows.
- Inspection utility `check-python` reports the status and installed packages of `.venv`.
