mkdir -p ~/.ssh
chmod 700 ~/.ssh
sops decrypt secrets/modal.toml > ~/.modal.toml
chmod 600 ~/.modal.toml
sops decrypt secrets/ssh-private-key > ~/.ssh/modal-sandbox
chmod 600 ~/.ssh/modal-sandbox
mkdir -p ~/.gemini/antigravity-cli
sops decrypt secrets/antigravity-oauth-token.json > ~/.gemini/antigravity-cli/antigravity-oauth-token
chmod 600 ~/.gemini/antigravity-cli/antigravity-oauth-token