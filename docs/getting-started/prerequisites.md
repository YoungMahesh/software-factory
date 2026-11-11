# Prerequisites & Environment Setup

Before using Modal Sandboxes, set up your local development environment.

## 1. System Requirements

- **Operating System**: macOS, Linux, or WSL2 on Windows.
- **Python**: Version 3.11 or 3.12.
- **Git**: Installed and available in your `$PATH`.
- **OpenSSH Client**: For connecting to sandboxes via `ssh`.

## 2. Modal Account & CLI Authentication

Modal Sandboxes runs execution environments using [Modal](https://modal.com).

1. Create an account at [modal.com](https://modal.com) if you do not have one.
2. Install the Modal client and authenticate:

```bash
pip install modal
modal setup
```

The `modal setup` command will authenticate your local machine via your browser and save API tokens to `~/.modal.toml`.

## 3. Clone and Install `modal-sandboxes`

Clone the repository and install the project in editable mode with development dependencies:

```bash
git clone https://github.com/<org>/modal-sandboxes.git
cd modal-sandboxes

python3 -m venv .venv
source .venv/bin/activate

# Install package with CLI
pip install -e .

# Optional: Install documentation tools
pip install -e .[docs]

# Optional: Install test runner
pip install -e .[dev]
```

Verify that the CLI executable is registered:

```bash
modal-sandbox --help
```

## 4. Optional: Secrets and Advanced Integrations

For basic standalone sandboxes, **no credentials** beyond `modal setup` are required.

If you plan to use repository cloning, GitHub PR integration, or AI agent harnesses, create a local `.env` file from the example:

```bash
cp .env.example .env
```

Refer to the [Environment Variables Reference](../reference/environment.md) and [Secrets Architecture](../architecture/secrets.md) for full configuration details.
