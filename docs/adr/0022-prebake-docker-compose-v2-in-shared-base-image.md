# Pre-bake Docker Compose v2 in Shared Base Image

We decided to pre-install `docker-compose-v2` directly into the Shared Base Image (`shared/image.py`) via `base_image.apt_install()`, providing native Docker CLI plugin support (`docker compose`) across all sandboxes while strictly omitting legacy hyphenated symlinks (`docker-compose`). Pre-baking the Compose v2 plugin into the base image maintains 100% Modal layer caching parity between Standard and VM Sandboxes (per ADR 0011), ensuring Compose is instantly available when `dockerd` starts in VM Sandboxes while remaining inert in Standard Sandboxes.

## Considered Options

- **Install in a VM-only incremental image layer**: Rejected because diverging image definitions breaks Modal layer cache parity between Standard and VM Sandboxes and introduces build overhead.
- **Add `/usr/local/bin/docker-compose` symlink for legacy hyphenated syntax**: Rejected because modern Compose v2 operates natively as a Docker CLI plugin (`docker compose`), and omitting legacy shims enforces standard, modern Docker workflows without masking missing tooling.
- **Download standalone binary from GitHub releases**: Rejected because Ubuntu 24.04's universe package `docker-compose-v2` cleanly tracks system dependencies alongside `docker.io` and `docker-buildx` packages already managed via APT.
- **Pre-install `docker-compose-v2` in Shared Base Image via `apt_install` without symlinks**: Accepted because it maintains base layer caching parity, aligns with existing Ubuntu Docker packages, and provides standard `docker compose` execution out of the box.

## Consequences

- `docker-compose-v2` is added to `base_image.apt_install()` in `shared/image.py`.
- VM Sandboxes immediately support `docker compose` once `dockerd` initializes during container boot.
- Standard Sandboxes carry the plugin binary inertly without daemon overhead or runtime penalty.
- Invocations requiring the legacy hyphenated command (`docker-compose`) will fail; users and automation must use the standard `docker compose` command.
- Documentation in `sandbox/readme.md` is updated to reflect Docker Compose v2 support.
