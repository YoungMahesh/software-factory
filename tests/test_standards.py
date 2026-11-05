"""Repository standards and line budget ratchet tests.

Enforces ADR 0057 and AGENTS.md Universal File Line Budget (<= 500 lines).
"""

from pathlib import Path
import unittest

MAX_PHYSICAL_LINES = 500
EXCLUDED_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".modal"}


def get_repo_python_files(repo_root: Path) -> list[Path]:
    """Finds all Python files in the repository subject to the line budget."""
    py_files = []
    for p in repo_root.rglob("*.py"):
        if any(part in EXCLUDED_DIRS for part in p.parts):
            continue
        py_files.append(p)
    return py_files


class TestCodeStandards(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[1]

    def test_universal_file_line_budget(self):
        """All production and test Python files must not exceed 500 physical lines."""
        violations = []
        py_files = get_repo_python_files(self.repo_root)

        self.assertGreater(len(py_files), 10, "Sanity check: expected multiple python files in repo")

        for py_file in py_files:
            rel_path = py_file.relative_to(self.repo_root)
            line_count = len(py_file.read_text(encoding="utf-8").splitlines())
            if line_count > MAX_PHYSICAL_LINES:
                violations.append((str(rel_path), line_count))

        if violations:
            msg = (
                f"Universal File Line Budget violation (ADR 0057 / AGENTS.md):\n"
                f"The following {len(violations)} file(s) exceed the {MAX_PHYSICAL_LINES}-line limit:\n"
            )
            for file_path, lines in violations:
                msg += f"  • {file_path}: {lines} lines (+{lines - MAX_PHYSICAL_LINES})\n"
            msg += "\nDecompose oversized files into deep directory modules or subsystem suites."
            self.fail(msg)
