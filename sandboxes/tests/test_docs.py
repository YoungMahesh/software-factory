"""Unit tests for Zensical documentation configuration and strict build."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class TestDocsBuild(unittest.TestCase):
    """Test suite for documentation configuration and Zensical compilation."""

    def test_mkdocs_emoji_extension_configured(self):
        """Verify mkdocs.yml configures pymdownx.emoji for Material and Octicons rendering."""
        repo_root = (
            Path(__file__).resolve().parents[2]
            if (Path(__file__).resolve().parents[2] / "mkdocs.yml").is_file()
            else Path(__file__).resolve().parent.parent
        )
        mkdocs_path = repo_root / "mkdocs.yml"
        self.assertTrue(mkdocs_path.is_file(), "mkdocs.yml must exist at repo root")
        content = mkdocs_path.read_text(encoding="utf-8")
        self.assertIn("pymdownx.emoji:", content)
        self.assertIn("material.extensions.emoji.twemoji", content)
        self.assertIn("material.extensions.emoji.to_svg", content)

    def test_zensical_build_clean(self):
        """Verify zensical binary is available and builds documentation without warnings."""
        zensical_bin = shutil.which("zensical")
        if not zensical_bin:
            self.skipTest("zensical binary not installed in test environment")

        repo_root = (
            Path(__file__).resolve().parents[2]
            if (Path(__file__).resolve().parents[2] / "mkdocs.yml").is_file()
            else Path(__file__).resolve().parent.parent
        )
        with tempfile.TemporaryDirectory():
            res = subprocess.run(
                [zensical_bin, "build", "--strict", "-f", str(repo_root / "mkdocs.yml")],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            site_dir = repo_root / "site"
            if site_dir.exists():
                shutil.rmtree(site_dir)

            self.assertEqual(
                res.returncode,
                0,
                f"zensical build --strict failed:\n{res.stderr}\n{res.stdout}",
            )


if __name__ == "__main__":
    unittest.main()
