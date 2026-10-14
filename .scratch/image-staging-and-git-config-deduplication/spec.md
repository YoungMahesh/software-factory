# Spec: Modal Image File Staging and Git Configuration Deduplication

Status: ready-for-agent
Triage: ready-for-agent

## Problem Statement

As the software factory sandbox image configuration expanded to support additional agent tooling, developer shortcuts, and multi-identity Git routing, repetitive boilerplate accumulated in the image definition module and configuration files:

1. **Repetitive File Staging Logic**: Staging local host assets into Modal images repeatedly invoked three-line guard blocks (`if path.exists(): image = image.add_local_file(path, target, copy=True)`). This boilerplate was duplicated across the Shared Base Image and within individual feature flag blocks in the sandbox image builder, cluttering image definitions and creating maintenance drag whenever new tooling assets are provisioned.
2. **Redundant Git Authorship Declaration**: The secondary Git configuration profile (`shared/gitconfig-mahesh471978`) duplicates user name configuration (`name = Mahesh`) already provided globally by the primary Git configuration (`shared/gitconfig`). Because Git's `includeIf` conditional inclusion mechanism natively inherits settings from the parent configuration, repeating the user name introduces unneeded duplication and risks author metadata drift if the base name is ever altered.
3. **Mismatched Test Boundaries**: Automated verification for Sandbox Git Configuration was appended directly into the test suite for Sandbox Shell Aliases (`TestSandboxShellAliases`), conflating distinct domain entities and duplicating filesystem fixture verification.

Developers and maintainers need a concise, declarative mechanism for staging local files into Modal images, clean single-source-of-truth Git identity routing, and well-structured, domain-aligned automated tests.

## Solution

1. **Declarative Image File Staging**: Introduce a batch helper function (`add_local_files_if_present`) that iterates over pairs of local paths and remote container destinations, conditionally staging existing files into a `modal.Image`. Expose a declarative public manifest (`BASE_IMAGE_FILES`) enumerating the foundational files staged into the Shared Base Image, and adopt the batch helper across all feature blocks (`opencode`, `agy`, `modal_tooling`) in the sandbox image construction pipeline.
2. **Backwards-Compatible Constant Exports**: Retain all existing module-level path constants (`LOCAL_*` and `REMOTE_*`) to ensure that external scripts, spawner modules, and integration test suites remain stable and decoupled from internal image construction refactoring.
3. **Inherited Git Profile Delta**: Refactor the secondary Git configuration profile (`shared/gitconfig-mahesh471978`) into a pure override delta containing strictly `[user] email = mahesh471978@gmail.com`, allowing Git's native configuration cascading to supply `name = Mahesh` from the primary global configuration.
4. **Dedicated Test Fixture & Offline Resolution Verification**: Separate Git configuration tests into a dedicated `TestSandboxGitConfig` test class aligned with domain concepts in `CONTEXT.md`. Assert declarative registration in `BASE_IMAGE_FILES`, verify absence of redundant authorship keys in the secondary profile, and include an offline Git identity resolution test verifying that conditional routing (`includeIf`) correctly resolves both default and overridden credentials.

## User Stories

1. As a developer maintaining sandbox images, I want foundational container assets declared in a concise list of path tuples, so that adding new files to the base image requires only a single manifest entry.
2. As a developer adding optional agent tooling to the sandbox image builder, I want to stage feature-specific files using a batch helper, so that I do not have to write repetitive existence checks and copy arguments.
3. As an engineer invoking sandbox CLI runners and test scripts, I want all exported `LOCAL_*` and `REMOTE_*` path constants preserved at module scope, so that existing imports across spawner and test utilities do not break.
4. As a developer maintaining Git identity profiles, I want secondary identity files to specify only the fields they override, so that shared identity fields like user name are maintained in a single source of truth.
5. As an operator running repositories routed through conditional Git configurations, I want Git's native `includeIf` mechanism to merge global name authorship with scoped email overrides, so that commits within designated directories reflect the correct identity seamlessly.
6. As a contributor reviewing automated test suites, I want Sandbox Git Configuration tests isolated in their own `TestSandboxGitConfig` test class, so that test structure accurately reflects the domain entities defined in `CONTEXT.md`.
7. As a test engineer running unit tests locally, I want an offline test verifying Git's cascading configuration resolution, so that conditional identity routing is deterministically validated without requiring live Modal container provisioning.
8. As a developer inspecting the image definition module, I want public access to the base image file manifest (`BASE_IMAGE_FILES`), so that automated tests can assert file registration directly against the manifest rather than inspecting opaque image layers.
9. As a developer adding new shell shortcuts or Git profiles, I want image staging errors prevented when optional secret or alias files are absent, so that container image construction remains robust across development environments.
10. As a code reviewer, I want boilerplate reductions to preserve all existing external behaviors and container paths, so that no regression in deployed sandbox functionality occurs.
11. As a maintainer auditing domain standards, I want the codebase to strictly adhere to terms in `CONTEXT.md` (Shared Base Image, Sandbox Git Configuration, Sandbox Shell Aliases), so that project documentation and implementation remain synchronized.
12. As a quality engineer running CI pipelines, I want all existing test suites (`test_sandbox.py`, `test_preview.py`, `test_ui.py`) to pass cleanly following the refactor, so that continuous verification guarantees stability.

## Implementation Decisions

- **Batch File Staging Helper**:
  Create a helper function `add_local_files_if_present` that accepts a `modal.Image` and an iterable of `(local_path, remote_path)` tuples. For each tuple where the local path exists on the host filesystem, the helper invokes `image.add_local_file(local_path, remote_path, copy=True)` and returns the resulting image.

- **Declarative Base Image Manifest**:
  Define a public list `BASE_IMAGE_FILES` containing the local-to-remote tuples for `startup.sh`, `aliases.bash`, `gitconfig`, `gitconfig-mahesh471978`, `setup.sh`, and `cloudflare.env`. Apply this manifest directly to the Shared Base Image definition via the batch helper.

- **Feature-Flagged Staging Consolidation**:
  Within the sandbox image construction pipeline, replace multiple sequential `if path.exists(): image = image.add_local_file(...)` calls for OpenCode, Antigravity CLI, and Modal tooling with calls to `add_local_files_if_present` passing lists of relevant path tuples.

- **Preservation of Module-Level Public Constants**:
  Maintain all individual `LOCAL_*` and `REMOTE_*` constant variables in the image module to prevent breaking external callers across the spawner, dispatcher, and automated test suites.

- **Pure Delta for Secondary Git Configuration**:
  Remove `name = Mahesh` from `shared/gitconfig-mahesh471978`, leaving only `[user] email = mahesh471978@gmail.com`. Git's configuration parser cascades `includeIf` blocks over global settings, ensuring that `name = Mahesh` declared in `shared/gitconfig` is retained when commits are authored within matched repository paths.

- **Domain-Aligned Test Separation**:
  Extract Git configuration testing from `TestSandboxShellAliases` into a standalone `TestSandboxGitConfig` test class.

## Testing Decisions

- **What makes a good test**:
  Tests must verify observable external interfaces and invariants—such as presence of files in declarative manifests, absence of redundant keys in configuration files, and end-to-end Git identity resolution behavior—without asserting on private internal loop variables or ephemeral container build states.

- **Modules to be tested**:
  - Image definition module (`shared.image`): Verify `BASE_IMAGE_FILES` contains the required file mappings and that `add_local_files_if_present` correctly adds existing files and skips missing ones.
  - Git configuration module (`shared/gitconfig*`): Verify base configuration contains default email and `includeIf` directive, verify secondary profile contains override email without duplicate name, and verify Git CLI identity resolution under simulated repository paths.
  - Startup script (`shared/startup.sh`): Verify inline dynamic `git config --global` mutations remain absent.

- **Prior art**:
  - `tests/test_sandbox.py` (`TestSandboxShellAliases`): Existing test patterns for validating staged files and startup script contents.
  - `tests/test_sandbox.py` (`TestSandboxCliArgs`): Existing temporary repository creation and git CLI execution patterns.

## Out of Scope

- Modifying shell script daemons (`startup.sh` and `factory_entrypoint.sh` Docker, swapfile, or Cloudflare background watchers).
- Modifying Git alias definitions in `shared/aliases.bash`.
- Altering Modal sandbox execution runners or container provisioning arguments.
- Introducing a runtime database or configuration server for Git identities.

## Further Notes

- Aligns directly with domain concepts in `CONTEXT.md`: [Shared Base Image](file:///root/software-factory/CONTEXT.md#L121-L123) and [Sandbox Git Configuration](file:///root/software-factory/CONTEXT.md#L109-L111).
- Per the project's Conditional ADR Policy, this internal refactoring introduces no irreversible trade-offs or surprising architectural patterns, so an ADR is omitted.
