# Externalize SSH Private Key Management and Decouple Sandbox Runners

Previously, the repository standardized on a dedicated repository key pair where the private key was encrypted with SOPS at `secrets/ssh-private-key`, decrypted locally to `~/.ssh/modal-sandbox` via `scripts/setup.sh`, and launch runners aborted early if `~/.ssh/modal-sandbox` was not present on the host machine. We decided to completely externalize SSH private key management: `secrets/ssh-private-key` has been removed from the repository, `scripts/setup.sh` no longer decrypts SSH keys, and sandbox runners validate only the public key tracked at `shared/ssh-key.pub`. Developers maintain the matching private key out-of-band at `~/.ssh/modal-sandbox` (or update `shared/ssh-key.pub` if rotated), allowing sandbox launch scripts to run in headless, CI/CD, or automated container environments without inspecting or depending on host workstation credentials.

## Considered Options

- **Enforce host private key existence on launch**: Check for `~/.ssh/modal-sandbox` on the host machine before creating sandboxes. Rejected because it couples sandbox provisioning to workstation filesystem state, breaking headless executions, automated orchestrators, and environments where sandboxes are launched remotely.
- **Track encrypted private keys in repository secrets (`secrets/ssh-private-key`)**: Store the encrypted private key in the repo and decrypt it via `scripts/setup.sh`. Rejected because sandbox containers only require the public key in `/root/.ssh/authorized_keys` to accept connections, and tracking the private key in repo secrets created unnecessary credential exposure and complex opt-in flags for sandbox bootstrapping.
- **Externalize private key ownership and decouple runners from host filesystem**: Track only `shared/ssh-key.pub` in version control, delete `secrets/ssh-private-key`, eliminate SSH decryption from `scripts/setup.sh`, and require runners to inspect only `shared/ssh-key.pub`. Accepted because it treats the sandbox runner purely as an infrastructure provisioning agent, leaves client credential ownership out-of-band, and enables zero-dependency sandbox launches.

## Consequences

- `secrets/ssh-private-key` is deleted from the repository.
- `scripts/setup.sh` no longer manages or decrypts SSH private keys, focusing exclusively on opt-in Modal client credentials (`--modal`) and Antigravity OAuth tokens.
- `standard_sandbox/main.py` and `vm_sandbox/main.py` only validate the existence of `shared/ssh-key.pub` and never inspect or require `~/.ssh/` on the launch computer.
- Connection output snippets in `print_access_info` continue to reference `-i ~/.ssh/modal-sandbox` as the default client key path for developers.
- Externalizes host private key validation and eliminates repository private key tracking.
