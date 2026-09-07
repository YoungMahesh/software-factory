Check modal version:
```bash
# Activate the virtual environment
source .venv/bin/activate
# Deactivate the virtual environment
deactivate 2>/dev/null

# if virtual env is activated
modal --version
modal app list
modal app stop <app-id|app-name>

# or directly using the binary path:
.venv/bin/modal --version

# upgrade
pip install --upgrade modal

# authenticate
python3 -m modal setup
# credentials will be stored at: ~/.modal/toml
```

Run code:
```bash
modal run get_started.py

python launch-opencode.py --secret-collection <modal-secret-collection-name>
```
