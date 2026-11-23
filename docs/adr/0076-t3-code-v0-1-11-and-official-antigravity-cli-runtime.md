# T3 Code v0.1.11 and Official Antigravity CLI Runtime

**Status**: Accepted (Amends [ADR 0025](0025-t3-code-server-and-agent-control-surface.md), [ADR 0035](0035-multi-account-antigravity-provider-instances-in-t3-code.md), and [ADR 0075](0075-retire-herdr-pi-opencode-agy-in-favor-of-t3.md))

We upgrade our pinned T3 Code distribution from `v0.1.3` to `v0.1.11` (`pingdotgg/t3code`), migrate the bundled Antigravity ACP runtime from the legacy Python PAR bundle (`agy-acp-server-1.3.0`) to the official Google Antigravity standalone CLI (`v1.5.14`), and streamline our binary patching surface by retiring obsolete IPv6 and model manifest patches while preserving our length-preserving SSH host alias and provider driver precedence patches.

## Context

In [ADR 0025](0025-t3-code-server-and-agent-control-surface.md) and [ADR 0075](0075-retire-herdr-pi-opencode-agy-in-favor-of-t3.md), we standardized on T3 Code (`t3 serve`) as the singular agent control surface running in Modal sandboxes.
The container image pre-downloaded Google's `agy-acp-server-1.3.0-linux-x86_64.zip` into `/root/.t3/tools/antigravity-acp/linux-x64/` with an installation record targeting `agy_acp_server.par` and `localharness_external`. Furthermore, we maintained five length-preserving in-place binary patches on the Node SEA binary (`/opt/t3/t3`):
1. IPv6 patch (`--enforce_kernel_ipv6_support=false`) to satisfy gVisor networking under the legacy Python PAR harness.
2. SSH host resolution patch reading `process.env.T3_SSH_HOST` or `process.env.SANDBOX_NAME`.
3. Provider ordering patch prioritizing `antigravity` over `opencode`.
4. Manifest currentModels patch pruning non-high Gemini models.
5. Manifest models array patch commenting out legacy and non-high models.

Upstream T3 Code `v0.1.11` brings critical stability improvements, including:
- Upstream migration to the official Google Antigravity CLI auto-updater manifest, where T3 Code executes the compiled Go binary (`antigravity acp`) directly rather than legacy Python PAR archives.
- Introduction of newer Gemini models (`gemini-4-carbon`, `gemini-4-argon`, `gemini-3.8-flash`) while natively defaulting chat to `gemini-3.8-flash-high`.
- Upstream fix stopping managed Antigravity CLI from self-updating in place and recovering on reinstall.
- Support for browser tunnels, port forwarding, and background command lifecycle improvements.

## Decisions

1. **Upgrade Pinned T3 Code Binary**:
   - Update `T3_VERSION` in `shared/image.py` from `0.1.3` to `0.1.11` (`t3-0.1.11-linux-x64.tar.gz`).

2. **Prebake Official Google Antigravity CLI Runtime**:
   - Update `shared/image.py` to download and stage the official Google Antigravity CLI v1.5.14 (`https://storage.googleapis.com/antigravity-public/antigravity-cli/1.5.14-5302690847260672/linux-x64/cli_linux_x64.tar.gz`) directly into `/root/.t3/tools/antigravity-acp/linux-x64/versions/83311d3f354567612dc16c1ae2ea9b503d6f6833aa4e138d39aa229da3f3bb99/antigravity`.
   - Generate `.install-complete.json` conforming to v0.1.11's single-executable schema (`{"releaseId":"83311d3f...","version":"1.5.14","executable":{"name":"antigravity","bytes":273240776}}`) and point `active.json` to this releaseId.
   - This eliminates on-demand runtime downloads during sandbox startup, guaranteeing deterministic, zero-network cold boots.

3. **Streamline Binary Patches in `shared/t3_patches.py`**:
   - **Retire IPv6 Patch**: Upstream spawns `antigravity acp` directly without Python PAR flags. Container environment variables (`FLAGS_enforce_kernel_ipv6_support=false`) remain active.
   - **Retire Model Manifest Pruning**: Retain upstream's native model catalog without byte-level regex comment surgery in the SEA binary. Model selection and defaults remain strictly managed via [ADR 0064](0064-default-antigravity-text-and-source-control-writer-model-in-t3-code.md) in `settings.json`.
   - **Preserve SSH Target Patch**: The 248-byte length-preserving patch matches verbatim in v0.1.11, routing SSH links to `process.env.T3_SSH_HOST` or `process.env.SANDBOX_NAME`.
   - **Update Driver Order Patch**: Upstream v0.1.11 appended `"kiro"` to `BUILT_IN_DRIVER_ORDER`. Update the 127-byte patch to swap `"opencode"` and `"antigravity"` within the updated 8-driver array.

4. **Synchronize Glossary and Documentation**:
   - Update the Antigravity Provider definition in `GLOSSARY.md` to reference the official `antigravity` CLI runtime instead of `agy_acp_server.par`.

5. **Modernize `t3 serve` Launch Arguments**:
   - Upstream v0.1.11 replaced the legacy `--auto-bootstrap-project-from-cwd <dir>` option with a standard positional working directory argument (`t3 serve [flags] [<cwd>]`).
   - Updated `shared/startup.sh` to launch `t3 serve --host 0.0.0.0 --port "$T3_PORT" --mode web "$TARGET_DIR"`.

## Consequences

- **Modernized Runtime**: Sandboxes benefit from upstream T3 Code v0.1.11 enhancements, latest ACP protocol updates, and official Google Antigravity CLI v1.5.14 stability.
- **Reduced Fragility**: Eliminating model manifest binary redaction avoids patching hundreds of bytes of JSON strings in compiled SEA assets across minor T3 Code point releases.
- **Fast Sandbox Provisioning**: Prebaking the 273MB `antigravity` binary into the shared Modal base image ensures instantaneous T3 Code server availability upon launch.
