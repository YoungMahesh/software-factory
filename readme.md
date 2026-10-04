Check modal version:
```bash
# Activate the virtual environment
source .venv/bin/activate
# Deactivate the virtual environment
deactivate

# if virtual env is activated
modal --version
modal app list
modal app stop <app-id|app-name>

# or directly using the binary path:
.venv/bin/modal --version

# install or upgrade dependencies
pip install -r requirements.txt

# authenticate
python3 -m modal setup
# credentials will be stored at: ~/.modal/toml
```

### Setup credentials:
```bash
# Decrypt both Modal client credentials and Antigravity tokens:
bash scripts/setup.sh --modal --agy

# Or decrypt individually:
bash scripts/setup.sh --modal    # Modal credentials only (~/.modal.toml)
bash scripts/setup.sh --agy      # Antigravity token only (~/.gemini/antigravity-cli/)
```

Encrypt/Decrypt file:
```bash
sops encrypt --in-place secrets/file1
sops decrypt secrets/file1
```

### If repository directory is moved or renamed

Python virtual environments contain hardcoded absolute paths. If you rename or move the repository folder, recreate `.venv`:

```bash
# Deactivate if currently active
deactivate

# Delete and recreate the virtual environment
rm -rf .venv
python3 -m venv .venv

# Activate and reinstall dependencies
source .venv/bin/activate
pip install -r requirements.txt
```
