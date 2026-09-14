```bash
# Launch OpenCode sandbox with SSH
python launch-with-opencode.py --secret-collection <modal-secret-collection-name>

# Custom SSH key and timeout
python launch-with-opencode.py \
    --secret-collection <modal-secret-collection-name> \
    --ssh-key ~/.ssh/id_ed25519 \
    --timeout 12h
```

