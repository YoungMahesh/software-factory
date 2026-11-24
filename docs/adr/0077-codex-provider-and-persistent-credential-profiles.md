# Codex Provider and Persistent Credential Profiles

**Status**: Accepted.

New T3 Code sandboxes will include Codex. A configured pool of Codex Credential Profiles will let trusted launches start signed in with ChatGPT and carry refreshed credentials across sandbox replacements. Each profile gets its own Modal Volume and is reserved for one running sandbox at a time. The project Apps and `<app-name>-<random-id>` sandbox names from [ADR 0029](0029-constant-modal-app-and-named-sandboxes.md) remain the basis for discovery and SSH.

## Implementation plan

1. **Install and configure Codex.** Pin the official Codex CLI to `0.171.0` in the T3 image layer and expose it to both the T3 server and SSH shells. Enable the native `codex` provider alongside Antigravity and OpenCode. Keep Antigravity as the default for new text generation and source-control writer settings under [ADR 0064](0064-default-antigravity-text-and-source-control-writer-model-in-t3-code.md). Preserve explicit model selections when the provider is available. Apply installation to newly built `--t3` and `--t3code` sandboxes. Older filesystem snapshots retain their original tooling and are outside the first rollout.

2. **Create profiles on demand.** A trusted workspace and environment can configure `CODEX_PROFILE_VOLUME_PREFIX`. Each profile uses a Modal Volume v2. The launcher mounts the `codex-home` subdirectory as `CODEX_HOME` for T3 and SSH. The allocator's `owner.json` stays outside the mounted subdirectory. Install `codexprofile` globally. `current` shows the attachment and `login` starts device sign-in and commits the saved login. A current session can seed the first volume after its original Codex processes stop. Further profiles can be signed into when first assigned.

3. **Select and record an owner in the existing launcher.** Read the volume records and prefer a free profile with a saved login. Record the normal App and sandbox name before creation, tag the sandbox with the attempt name, and then save the sandbox ID. The launcher assumes that users initiate launches one at a time. Already running sandboxes can overlap. Simultaneous launches can select the same volume because volume writes are last-write-wins. CLI and dashboard use the same launcher logic, with no separate allocator or reservation backend.

4. **Reuse after exit.** Reconcile owner records with Modal, including a name and attempt tag check when the create response was lost. Keep uncertain ownership unavailable. Release on confirmed exit. When there is no available profile, the sandbox can still start and use a local sign-in. The T3 usage volume is independent of the credential profiles.

5. **Report status.** Include the attached profile in the launch response. `codexprofile status` reports local login status and, when configured, calls a read-only control-plane endpoint with a short-lived workspace-scoped credential. Pool status reports whether a login file is saved, availability, and the owning sandbox name.

## Trade-offs

- Factory secret injection can supply a one-time seed. Persisting personal ChatGPT login state in a static `.env` would require a separate write-back path once Codex refreshes it. An API key would fit the existing injection pattern and use OpenAI API billing. [Codex authentication and refresh guidance](https://learn.chatgpt.com/docs/auth/ci-cd-auth)
- Modal Volumes persist the file Codex already updates and stay outside root filesystem snapshots. Modal Dict entries expire after seven days of inactivity, so a Dict is unsuitable as the durable credential store. [Modal Volume commits](https://modal.com/docs/guide/volumes#background-commits) · [Modal filesystem snapshots](https://modal.com/docs/guide/sandbox-snapshots) · [Modal Dict retention](https://modal.com/docs/guide/dicts)
- Using fixed Modal sandbox names to reserve profiles would require grouping those sandboxes under one App. Volume owner records keep the agreed project Apps and sandbox names. [Modal named sandbox scope](https://modal.com/docs/guide/sandboxes#named-sandboxes)

## Verification before rollout

- Run `pytest`, including the repository line budget. Cover image and provider discovery, local and hosted launch paths, profile selection with overlapping running sandboxes, a fourth launch with no free profile, and recovery after timeout or an ambiguous create response.
- Verify the supported live flow against the [Test Repository Baseline](../guides/cli.md#command-options). Use dedicated test profiles. Confirm Codex works through T3, simultaneous test sandboxes receive different profiles, and a replacement starts signed in after its predecessor exits. Confirm that auth stays outside snapshots and shared transcript synchronization. Terminate test sandboxes immediately after verification.
