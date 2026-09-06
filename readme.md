Check modal version:
```bash
# if virtual env is activated
modal --version

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
``
