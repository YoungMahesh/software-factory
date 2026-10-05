# Automated OpenCode and MCP Credentials Provisioning via SOPS

Previously, OpenCode server and remote Model Context Protocol (MCP) integrations (Exa, Context7) required manual credential configuration after sandbox initialization, and `OPENCODE_GO_API_KEY` set via environment variables did not register in OpenCode WebUI without account integration. We decided to automate credential provisioning through SOPS: `secrets/opencode.env` stores encrypted API keys (`OPENCODE_GO_API_KEY`, `EXA_API_KEY`, `CONTEXT7_API_KEY`), `scripts/setup.sh` decrypts them via a new `--opencode` flag to `~/.config/opencode/opencode.env` and exports them to the environment, `shared/opencode.json` configures MCP servers using `{env:...}` header substitution, and sandbox startup scripts register OpenCode Go via OpenCode's local REST API upon server readiness.

## Considered Options

- **Manual interactive setup via OpenCode CLI/WebUI**: Require users to run `opencode auth login` or enter keys in the WebUI manually on every ephemeral sandbox creation. Rejected because it disrupts automated workflows and `opencode auth login` refuses non-interactive TTY input.
- **Direct SQLite database injection prior to server startup**: Write credentials directly into `/root/.local/share/opencode/opencode.db` using a custom Python script. Rejected because it couples container bootstrap to internal SQLite schemas and credential serialization formats that can drift across OpenCode releases.
- **Process-scoped environment without `/etc/environment` or `~/.bashrc` export**: Source `opencode.env` strictly for the `opencode serve` command. Rejected because subshells spawned by OpenCode and developer terminal/SSH sessions need ambient access to `EXA_API_KEY` and `CONTEXT7_API_KEY` for CLI tools and scripts.
- **Automated SOPS decryption with strict fail-fast and REST API registration**: Extend `scripts/setup.sh` with an orthogonal `--opencode` flag, decrypt `secrets/opencode.env` during SOPS bootstrap in `startup.sh`, source the variables before running `opencode serve`, and register the OpenCode Go key via `POST /api/integration/opencode-go/connect/key` once the server port is responsive. Accepted because it maintains consistency with ADR-0007 and ADR-0008, uses OpenCode's supported REST API contract, and secures keys at rest using existing Age recipients.

## Consequences

- `scripts/setup.sh` accepts `--opencode` (decrypts `secrets/opencode.env` to `~/.config/opencode/opencode.env` mode 0600) and exports key-value pairs into `/etc/environment` (if writable) and `~/.bashrc`.
- `shared/opencode.json` configures remote MCP server `exa` with header `"x-api-key": "{env:EXA_API_KEY}"` and `context7` with `"oauth": false` and header `"CONTEXT7_API_KEY": "{env:CONTEXT7_API_KEY}"`.
- `standard_sandbox/startup.sh` and `vm_sandbox/startup.sh` include `--opencode` when `ENABLE_OPENCODE=1`, trigger SOPS decryption, export the environment before launching `opencode serve`, and invoke OpenCode's local integration API to register `OPENCODE_GO_API_KEY`.
- If `ENABLE_OPENCODE=1` is passed to sandbox runners but `AGE_PRIVATE_KEY` is missing from the secret collection, sandbox creation fails fast with an explicit error.
