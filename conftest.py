import sys
from pathlib import Path

# Ensure repository root and sandboxes/ are on sys.path for test discovery and imports
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SANDBOXES = ROOT / "sandboxes"
if str(SANDBOXES) not in sys.path:
    sys.path.insert(0, str(SANDBOXES))
