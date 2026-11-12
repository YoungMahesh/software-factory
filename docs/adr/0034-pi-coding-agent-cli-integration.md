# Pi Coding Agent CLI Integration

**Status**: Accepted (Amends [ADR 0005](0020-opencode-go-provider-and-target-project-prerequisite.md))

To provide developers with an interactive, terminal-native AI coding agent inside Modal Sandboxes alongside Antigravity, OpenCode, and T3 Code, we decided to integrate the **Pi Coding Agent CLI** (`pi.dev`) via a dedicated `--pi` launch flag, pre-configured with OpenCode Go and DeepSeek V4.1 Flash.

## Considered Options

- **Manual Interactive Setup in Sandbox Sessions**: Requiring developers to run `curl -fsSL https://pi.dev/install.sh | bash` and authenticate manually via `/login` upon attaching over SSH or shell. Rejected because manual setup delays developer workflows, requires repeated credential re-entry across ephemeral sandboxes, and risks credential leaks in bash history.
- **Dynamic Startup Generation of Configuration**: Generating `~/.pi/agent/settings.json` dynamically inside `startup.sh` via inline bash heredocs. Rejected because dynamic scripts obscure agent configuration from version control and break declarative parity with existing shared tooling configs (`shared/opencode.json`, `shared/antigravity-settings.json`).
- **Declarative Staging of Shared Configuration with SOPS Decryption**: Pre-baking the global CLI package (`@earendil-works/pi-coding-agent`) via npm, tracking declarative agent configuration files (`shared/pi-settings.json` and `shared/pi-models.json`) in version control, and orchestrating ephemeral SOPS decryption of `secrets/opencode.env` during container initialization. Accepted because it delivers instantaneous agent availability upon SSH attachment, maintains version-controlled configurations, and reuses established SOPS credential management.

## Consequences

- **CLI Flag (`--pi`)**: Added to `sandbox/cli.py` and `sandbox/main.py`. Mutual exclusivity with `--snapshot` is enforced.
- **Declarative Configuration**:
  - `shared/pi-settings.json` sets `defaultProvider: "opencode-go"` and `defaultModel: "deepseek-v4.1-flash"`, staged to `/root/.pi/agent/settings.json`.
  - `shared/pi-models.json` registers the `opencode-go` provider endpoint (`https://opencode.ai/zen/go/v1`) using `$OPENCODE_GO_API_KEY`, staged to `/root/.pi/agent/models.json`.
- **Image Layering (`shared/image.py`)**:
  - Installs `@earendil-works/pi-coding-agent` globally via npm in the container filesystem.
  - Stages `LOCAL_PI_SETTINGS`, `LOCAL_PI_MODELS`, and `LOCAL_OPENCODE_SECRET` into the container image.
- **Lifecycle & Secrets (`shared/startup.sh` and `scripts/setup.sh`)**:
  - Passing `--pi` triggers `setup.sh --pi`, ephemerally decrypting `secrets/opencode.env` with `AGE_PRIVATE_KEY`.
  - Exports `OPENCODE_GO_API_KEY` and `OPENCODE_API_KEY` into `~/.bashrc` and `/etc/environment` for subshell and login shell availability.
  - Staged secrets in `/root/secrets/` are scrubbed following decryption.
- **Domain Modeling**: The canonical term **Pi Coding Agent CLI** is added to `CONTEXT.md`.
- **Universal File Line Budget**: All modified files remain strictly <= 500 lines.
