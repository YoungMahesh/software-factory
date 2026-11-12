# Default Antigravity Text Generation and Source Control Writer Model in T3 Code

**Status**: Accepted (Amends [ADR 0025](0025-t3-code-server-and-agent-control-surface.md) and [ADR 0035](0035-multi-account-antigravity-provider-instances-in-t3-code.md))

We pre-configure `sourceControlWriterModelSelection` and `textGenerationModelSelection` in T3 Code server settings (`/root/.t3/userdata/settings.json`) to use Google Antigravity Gemini 3.8 Flash (Low) (`gemini-3.8-flash-low`). When sandboxes are booted with `--t3` or `--t3code`, the initialization routines in `shared/startup.sh` and `scripts/setup.sh` dynamically select the active authenticated Antigravity account instance (preferring `antigravity-anv`, then `antigravity-mgh`, then `antigravity`), preventing pull request creation and text generation failures in the T3 Code Web UI.

## Context

When creating pull requests, generating commit messages, or drafting branch names from the T3 Code Web UI, T3 Code calls `resolveSourceControlWriterModelSelection(settings)` which checks `settings.sourceControlWriterModelSelection` and falls back to `settings.textGenerationModelSelection`.

In unconfigured environments, T3 Code falls back to its built-in binary default: `{ instanceId: "codex", model: "codex-default" }`. Because the Codex provider instance is disabled by default in Modal sandboxes (`providerInstances.codex.enabled: false`), invoking pull request creation or text generation fails immediately with an unhandled provider error ("Provider instance is disabled").

## Considered Options

- **Manual Selection in Web UI**: Requiring developers to navigate to Project Settings or Model Preferences in the Web UI to choose a text generation model. Rejected because creating pull requests is a primary developer action and should work reliably out of the box on first boot.
- **Defaulting to Gemini 3.8 Flash (High)**: Configuring the primary reasoning model `gemini-3.8-flash-high`. Rejected because text drafting tasks such as PR title/body generation and branch naming are lightweight operations where low-latency models (`gemini-3.8-flash-low`) provide near-instant responses while conserving quota windows.
- **Hardcoded Account Instance ID**: Hardcoding `instanceId: "antigravity"` or `"antigravity-anv"`. Rejected because sandboxes may be provisioned with varying account profiles (`m47`, `mgh`, or `anv`). Statically hardcoding an instance risks referencing an unauthenticated or missing profile.
- **Dynamic Active Instance Resolution**: Checking provisioned Antigravity credentials during container startup, prioritizing verified working accounts (`antigravity-anv`, then `antigravity-mgh`, then `antigravity`), and applying the selected `instanceId` to `sourceControlWriterModelSelection` and `textGenerationModelSelection` whenever unset or set to the disabled `codex` fallback. Accepted.

## Consequences

- **Startup Scripts (`shared/startup.sh` and `scripts/setup.sh`)**:
  - Dynamically identify provisioned Antigravity provider instances during startup.
  - Automatically configure `sourceControlWriterModelSelection` and `textGenerationModelSelection` to `{ "instanceId": default_agy_instance, "model": "gemini-3.8-flash-low" }` in `/root/.t3/userdata/settings.json`.
  - Preserve any user-modified model configurations while overwriting unset or disabled `codex` defaults.
- **Immediate Web UI Functionality**: Developers can immediately draft and create pull requests, generate commit summaries, and suggest branch names in T3 Code Web UI without configuration errors.
- **Test Coverage**: Added test coverage in `tests/test_sandbox/test_t3_code.py` verifying both script content and end-to-end multi-account prioritization for model selection.
- **Universal File Line Budget**: All modified files and new ADRs remain within documented line limits.
