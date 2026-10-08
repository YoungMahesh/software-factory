from pathlib import Path
import subprocess
import unittest


class TestFactoryEntrypointScript(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent
        self.entrypoint_script = self.repo_root / "shared" / "factory_entrypoint.sh"

    def test_script_exists_and_executable(self):
        self.assertTrue(self.entrypoint_script.is_file())

    def test_bash_syntax_valid(self):
        res = subprocess.run(
            ["bash", "-n", str(self.entrypoint_script)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0, f"Bash syntax error: {res.stderr}")

    def test_help_flag(self):
        res = subprocess.run(
            ["bash", str(self.entrypoint_script), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("Usage:", res.stdout)
        self.assertIn("--feature <slug>", res.stdout)

    def test_missing_feature_fails(self):
        res = subprocess.run(
            ["bash", str(self.entrypoint_script)],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Feature slug is required", res.stderr)

    def test_missing_age_key_fails(self):
        res = subprocess.run(
            ["bash", str(self.entrypoint_script), "--feature", "test-feat"],
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("AGE_PRIVATE_KEY is not set", res.stderr)


if __name__ == "__main__":
    unittest.main()
