#!/usr/bin/env python3
"""Convenience launcher for the Modal Sandbox Runner Web UI."""

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sandbox.web import main

if __name__ == "__main__":
    sys.exit(main())
