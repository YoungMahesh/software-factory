#!/usr/bin/env bash
# DEPRECATED: Startup logic has been unified into shared/startup.sh
# See docs/adr/0011-unified-base-image-for-standard-and-vm-sandboxes.md
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/../shared/startup.sh" "$@"
