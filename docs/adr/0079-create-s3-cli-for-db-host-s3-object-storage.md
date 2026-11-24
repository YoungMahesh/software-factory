# Create-S3 CLI for db-host S3 Object Storage Provisioning and Management

**Status**: Accepted.

The software factory integrates with the hosted `db-host` control plane (SeaweedFS S3 object storage) to provision isolated S3 buckets, manage IAM credentials, and configure standard AWS SDK environment variables for factory sandboxes and developer repositories.

## Implementation details

1. **Standalone CLI Tool (`create-s3`).** Implement `create-s3` as a standalone command registered in `pyproject.toml` and symlinked to `/usr/local/bin/create-s3` and `/root/.scripts/create-s3`. This decouples S3 bucket lifecycle management from container provisioning while offering immediate availability in all sandbox environments.

2. **Domain Logic Separation (`sandbox/s3_host.py`).** To respect the universal 500-line budget limit enforced by `tests/test_standards.py`, core S3 client logic resides in a dedicated module `sandbox/s3_host.py` rather than overloading `sandbox/db_host.py`. It re-uses shared JSON-RPC MCP and `.env` updating utilities from `sandbox.db_host`.

3. **Environment & Authentication Configuration.** Re-uses `DB_HOST_DOMAIN` and `DB_HOST_ADMIN_TOKEN` from ambient environment or local `.env`, supporting ad-hoc overrides via `--domain` and `--token` flags.

4. **Client-side Bucket Name Validation.** Validates bucket names client-side before network calls according to S3/SeaweedFS naming rules (3–63 characters, lowercase alphanumeric and hyphens, starting and ending with alphanumeric characters).

5. **Project Scoping & Idempotency.** Project names default to the current Git repository name (via `detect_repo_name()`) or `"default"`, with `--project` override. Bucket provisioning is idempotent by default: if a bucket already exists, `create-s3` retrieves existing IAM credentials via `get_storage_credentials` and reports reuse (`already_existed=True`), unless `--fail-if-exists` is explicitly passed.

6. **Standard AWS SDK Environment Variable Injection.** `--write-env` injects or updates the 5 standard AWS SDK environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_ENDPOINT_URL_S3`, `AWS_REGION`, and `S3_BUCKET_NAME`) in `.env`. An optional `--prefix` flag allows scoping for multi-bucket configurations (e.g. `--prefix ASSETS_`).

7. **Central Vault Integration.** When `--write-env` is used with `--push-vault`, `create-s3` automatically executes `push-repo-env` to encrypt and synchronize the updated `.env` file into the central `env-store` vault.

8. **Turnkey Code Snippets & Output Modes.** Emits ready-to-use client snippets for Python (`boto3`), Node.js (`@aws-sdk/client-s3`), and AWS CLI. Supports `--json` for machine-readable JSON output and `-q` / `--quiet` for canonical S3 URI output (`s3://<bucket-name>`).
