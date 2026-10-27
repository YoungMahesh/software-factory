---
name: close-modal-sandboxes
description: Terminate or close running Modal sandboxes by instance name or ID, preserving specified sandboxes or closing unneeded ones. Use when the user asks to close, stop, terminate, or clean up Modal sandboxes.
---

# Close Modal Sandboxes

Safely inspect, filter, and terminate running Modal sandboxes without stopping or modifying deployed Modal applications.

## Key Rules

- **Sandbox vs App separation**: Always terminate individual `modal.Sandbox` instances (`sb.terminate()`). Never run `modal app stop`, which would kill the parent deployed application.
- **Identity resolution**: Modal sandboxes are identified either by Modal Sandbox ID (`sb-...`) or remote-control instance name (e.g., `software-factory-286b1142`). The instance name lives inside the container at `/tmp/agy-remote-control.log` or in sandbox tags.
- **Safety**: When closing all sandboxes except a whitelist, always verify the active list before terminating.

---

## Workflow Steps

### 1. Discover Active Sandboxes

Run the management script to list active sandboxes and their resolved instance names:

```bash
uv run python scripts/manage_sandboxes.py --list
```
*(Or use `/root/software-factory/.venv/bin/python scripts/manage_sandboxes.py --list`)*

Sample output:
```
Active Sandboxes (2 running / 2 total):
  sb-01M5YP243NZZN82DJRGHWMNVW6 [software-factory-286b1142]: RUNNING
  sb-01M5Y7WGTG191W0SZPZ4TNT1FP [software-factory-b15fb788]: RUNNING
```

### 2. Simulate or Validate Target Sandboxes

Before terminating, check the target list with `--dry-run`:

- **Close all except whitelist (keep specific sandboxes)**:
  ```bash
  uv run python scripts/manage_sandboxes.py --dry-run --keep software-factory-286b1142 software-factory-b15fb788
  ```

- **Terminate specific sandboxes**:
  ```bash
  uv run python scripts/manage_sandboxes.py --dry-run --terminate software-factory-bf5ba032 sb-01M5YMHXKWJX6KPWWPA6S6XDBR
  ```

### 3. Terminate Target Sandboxes

Execute the command without `--dry-run`:

```bash
uv run python scripts/manage_sandboxes.py --keep <NAME_OR_ID_TO_KEEP> ...
# or
uv run python scripts/manage_sandboxes.py --terminate <NAME_OR_ID_TO_TERMINATE> ...
```

### 4. Verify Active State

Confirm that:
1. Target sandboxes are terminated.
2. Preserved sandboxes are still `RUNNING`.
3. The deployed Modal App (`modal app list`) remains active in `deployed` state.

```bash
uv run python scripts/manage_sandboxes.py --list
```

---

## Python SDK Reference

To terminate sandboxes directly using Python:

```python
import modal

# 1. Terminate a specific sandbox by ID
sb = modal.Sandbox.from_id("sb-01M5YNJSW0Y66F8CCAGDZ845B9")
sb.terminate(wait=True)

# 2. Iterate and selectively terminate
app = modal.App.lookup("software-factory")
keep_ids = {"sb-01M5YP243NZZN82DJRGHWMNVW6", "sb-01M5Y7WGTG191W0SZPZ4TNT1FP"}

for sb in modal.Sandbox.list(app_id=app.app_id):
    if sb.poll() is None and sb.object_id not in keep_ids:
        sb.terminate(wait=True)
```
