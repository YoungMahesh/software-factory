"""Subsystem tests to ensure factory/ui/static/dist is fresh and matches frontend source."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DIST_DIR = REPO_ROOT / "factory" / "ui" / "static" / "dist"
FRONTEND_DIR = REPO_ROOT / "factory" / "ui" / "frontend"


class TestFrontendDistFreshness(unittest.TestCase):
    def test_dist_index_html_and_assets_exist(self):
        """Verifies that compiled index.html exists and references valid assets."""
        index_file = DIST_DIR / "index.html"
        self.assertTrue(index_file.is_file(), f"Expected {index_file} to exist. Run 'pnpm --dir factory/ui/frontend build'.")
        content = index_file.read_text(encoding="utf-8")
        self.assertTrue(len(content) > 0, "index.html is empty")

        # Find referenced JS bundle
        js_matches = re.findall(r'src=["\']/?assets/(index-[^"\']+\.js)["\']', content)
        self.assertTrue(len(js_matches) > 0, f"No JS bundle found referenced in {index_file}")

        for js_name in js_matches:
            js_path = DIST_DIR / "assets" / js_name
            self.assertTrue(js_path.is_file(), f"Referenced JS asset does not exist: {js_path}")

        # Find referenced CSS bundle
        css_matches = re.findall(r'href=["\']/?assets/(index-[^"\']+\.css)["\']', content)
        for css_name in css_matches:
            css_path = DIST_DIR / "assets" / css_name
            self.assertTrue(css_path.is_file(), f"Referenced CSS asset does not exist: {css_path}")

    def test_dist_bundle_no_deprecated_routes(self):
        """Verifies that the compiled JS bundle does not contain deprecated /api/studio/ routes."""
        index_file = DIST_DIR / "index.html"
        content = index_file.read_text(encoding="utf-8")
        js_matches = re.findall(r'src=["\']/?assets/(index-[^"\']+\.js)["\']', content)
        self.assertTrue(len(js_matches) > 0)

        js_path = DIST_DIR / "assets" / js_matches[0]
        js_content = js_path.read_text(encoding="utf-8")

        # Must not contain deprecated /api/studio/ prefixes
        self.assertNotIn(
            "/api/studio/",
            js_content,
            f"Compiled bundle {js_path.name} contains deprecated '/api/studio/' endpoints! "
            "Recompile with 'pnpm --dir factory/ui/frontend build'.",
        )

        # Must contain canonical /api/repos
        self.assertIn(
            "/api/repos",
            js_content,
            f"Compiled bundle {js_path.name} missing canonical '/api/repos' endpoint.",
        )

    def test_dist_freshness_clean_git_tree(self):
        """Verifies that running pnpm build yields zero uncommitted git diff in static/dist/."""
        if not shutil.which("pnpm"):
            self.skipTest("pnpm not installed in test environment")
        if not shutil.which("git"):
            self.skipTest("git not installed in test environment")

        # Check if in a git repository
        git_check = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        if git_check.returncode != 0:
            self.skipTest("Not inside a git repository")

        # Run pnpm build
        build_res = subprocess.run(
            ["pnpm", "--dir", str(FRONTEND_DIR), "build"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        self.assertEqual(
            build_res.returncode,
            0,
            f"pnpm build failed:\nSTDOUT:\n{build_res.stdout}\nSTDERR:\n{build_res.stderr}",
        )

        # Verify no uncommitted changes in factory/ui/static/dist/
        diff_res = subprocess.run(
            ["git", "status", "--porcelain", str(DIST_DIR)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        status_output = diff_res.stdout.strip()
        self.assertEqual(
            status_output,
            "",
            f"factory/ui/static/dist is out of sync with frontend source!\n"
            f"Diff status:\n{status_output}\n"
            f"Run 'pnpm --dir factory/ui/frontend build' and commit the updated static bundle.",
        )


if __name__ == "__main__":
    unittest.main()
