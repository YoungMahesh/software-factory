from pathlib import Path
import subprocess
import unittest


class TestSandboxCliArgs(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent
        self.sandbox_main = self.repo_root / "sandbox" / "main.py"

    def test_help_contains_sops_flag(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--sops", res.stdout)
        self.assertIn("Retain SOPS age private key", res.stdout)

    def test_missing_secret_fails(self):
        res = subprocess.run(
            ["python3", str(self.sandbox_main), "--sops"],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("the following arguments are required: -s/--secret", res.stderr)


if __name__ == "__main__":
    unittest.main()
