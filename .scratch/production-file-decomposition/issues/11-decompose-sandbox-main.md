# 11: Decompose sandbox/main.py

**What to build:**
Decompose `sandbox/main.py` (681 physical lines) by extracting CLI argument handling and credential preparation helpers into internal sub-modules:
- Extract `sandbox/cli.py`:
  - Argument parsing (`parse_args`), command-line validation, and terminal formatting helpers (including `generate_ascii_qr`).
- Extract `sandbox/config.py`:
  - Port constants (`DEFAULT_WEB_PORT`, `DEFAULT_OPENCODE_PORT`, `DEFAULT_METRO_PORT`, `DEFAULT_T3_PORT`), timeout constants, and volume setup helpers.
- Refactor `sandbox/main.py`:
  - Focus strictly on `run_sandbox()` orchestration: image construction, volume mounts, secret resolution, container launch, and SSH/tunnel instruction printing.
  - Target size for `sandbox/main.py`: $\le 300$ physical lines.
- Invariant: Each newly created file must be $\le 500$ physical lines (`wc -l`).
- Verification: Run `pytest tests/test_sandbox.py` to ensure sandbox provisioning logic and CLI arguments remain fully intact.

**Blocked by:** 10-decompose-factory-ui-db

**Status:** ready-for-agent
**Triage:** ready-for-agent

- [ ] Create `sandbox/cli.py` and extract CLI parsing and QR generation logic.
- [ ] Create `sandbox/config.py` and extract sandbox defaults, port constants, and volume configurations.
- [ ] Refactor `sandbox/main.py` to import from `cli.py` and `config.py`.
- [ ] Confirm all touched files are $\le 500$ physical lines.
- [ ] Verify `pytest tests/test_sandbox.py` passes without test modifications.
