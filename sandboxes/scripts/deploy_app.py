#!/usr/bin/env python3
"""Host-only CLI entrypoint for deploying Hosted Apps to the Resource Plane VPS."""

from __future__ import annotations

from pathlib import Path
import sys

_SANDBOXES_ROOT = Path(__file__).resolve().parent.parent
if str(_SANDBOXES_ROOT) not in sys.path:
    sys.path.insert(0, str(_SANDBOXES_ROOT))

from sandbox.app_deploy._cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
