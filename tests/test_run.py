import argparse
import io
from pathlib import Path
import subprocess
import unittest
from unittest.mock import MagicMock, patch

from factory.run import (
    DEFAULT_MODEL,
    SUPPORTED_MODELS,
    main,
    normalize_model_name,
    parse_args,
    validate_project_secrets,
)



class TestCliDispatcherArgs(unittest.TestCase):
    def test_parse_args_minimal(self):
        args = parse_args(["--project", "repo-horizon", "--feature", "auth-page"])
        self.assertEqual(args.project, "repo-horizon")
        self.assertEqual(args.feature, "auth-page")
        self.assertIsNone(args.issue)
        self.assertFalse(args.vm)
        self.assertFalse(args.testing)
        self.assertEqual(args.model, DEFAULT_MODEL)
        self.assertEqual(args.model, "deepseek-v4.1-flash")

    def test_parse_args_shorthand_flags(self):
        args = parse_args(["-p", "test3", "-f", "slug-gen", "-i", "01"])
        self.assertEqual(args.project, "test3")
        self.assertEqual(args.feature, "slug-gen")
        self.assertEqual(args.issue, "01")

    def test_parse_args_testing_flags(self):
        args1 = parse_args(["--project", "test3", "--feature", "slug-gen", "--testing"])
        self.assertTrue(args1.testing)

        args2 = parse_args(["--project", "test3", "--feature", "slug-gen", "--test"])
        self.assertTrue(args2.testing)

    def test_parse_args_vm_and_memory(self):
        args = parse_args(["--project", "test3", "--feature", "slug-gen", "--vm", "--memory", "4"])
        self.assertTrue(args.vm)
        self.assertEqual(args.memory_gb, 4)

    def test_model_normalization_default(self):
        self.assertEqual(normalize_model_name(None), "deepseek-v4.1-flash")
        self.assertEqual(normalize_model_name(""), "deepseek-v4.1-flash")

    def test_model_normalization_deepseek_variants(self):
        variants = [
            "DeepSeek V4.1 Flash",
            "deepseek-v4.1-flash",
            "deepseek",
            "deepseek-flash",
            "DEEPSEEK V4.1 FLASH",
        ]
        for v in variants:
            self.assertEqual(
                normalize_model_name(v),
                "deepseek-v4.1-flash",
                f"Failed for variant {v}",
            )

    def test_model_normalization_mimo_variants(self):
        variants = [
            "MiMo-V2.6-Flash",
            "mimo-v2.6-flash",
            "mimo",
            "mimo-flash",
            "MIMO-V2.6-FLASH",
            "MiMo V2.6 Flash",
        ]
        for v in variants:
            self.assertEqual(
                normalize_model_name(v),
                "mimo-v2.6-flash",
                f"Failed for variant {v}",
            )

    def test_model_normalization_unsupported(self):
        with self.assertRaises(ValueError) as ctx:
            normalize_model_name("gpt-4o")
        self.assertIn("Unsupported model", str(ctx.exception))

    def test_parse_args_model_flag(self):
        args_deepseek = parse_args(["--project", "p", "--feature", "f", "--model", "DeepSeek V4.1 Flash"])
        self.assertEqual(args_deepseek.model, "deepseek-v4.1-flash")

        args_mimo = parse_args(["--project", "p", "--feature", "f", "--model", "MiMo-V2.6-Flash"])
        self.assertEqual(args_mimo.model, "mimo-v2.6-flash")

        args_mimo_alias = parse_args(["--project", "p", "--feature", "f", "-m", "mimo"])
        self.assertEqual(args_mimo_alias.model, "mimo-v2.6-flash")

    def test_parse_args_missing_required(self):
        with patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                parse_args(["--project", "repo-horizon"])

        with patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                parse_args(["--feature", "auth-page"])


class TestLocalSecretValidation(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent

    def test_validate_project_secrets_production(self):
        path = validate_project_secrets("software-factory", testing=False, repo_root=self.repo_root)
        self.assertTrue(path.is_dir())
        self.assertTrue((path / "fetch.env").is_file())

    def test_validate_project_secrets_testing(self):
        path = validate_project_secrets("test3", testing=True, repo_root=self.repo_root)
        self.assertTrue(path.is_dir())
        self.assertTrue((path / "fetch.env").is_file())

    def test_validate_project_secrets_missing(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            validate_project_secrets("nonexistent-project", testing=False, repo_root=self.repo_root)
        self.assertIn("nonexistent-project", str(ctx.exception))

    @patch("factory.run.dispatch_job")
    def test_main_local_validation_failure_exits_without_modal(self, mock_dispatch):
        stderr_buf = io.StringIO()
        code = main(
            ["--project", "nonexistent-project", "--feature", "my-feature"],
            stderr=stderr_buf,
            repo_root=self.repo_root,
        )
        self.assertEqual(code, 1)
        self.assertIn("nonexistent-project", stderr_buf.getvalue())
        # Confirms cloud spawner was never invoked!
        mock_dispatch.assert_not_called()


class TestCliExecution(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent

    @patch("factory.run.dispatch_job")
    def test_main_successful_dispatch_propagates_exit_code_zero(self, mock_dispatch):
        mock_dispatch.return_value = 0
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        code = main(
            ["--project", "test3", "--feature", "slug-gen", "--testing"],
            stdout=stdout_buf,
            stderr=stderr_buf,
            repo_root=self.repo_root,
        )

        self.assertEqual(code, 0)
        mock_dispatch.assert_called_once_with(
            project="test3",
            feature="slug-gen",
            issue=None,
            vm=False,
            testing=True,
            model="deepseek-v4.1-flash",
            memory_gb=None,
            stdout=stdout_buf,
            stderr=stderr_buf,
        )

    @patch("factory.run.dispatch_job")
    def test_main_with_all_options(self, mock_dispatch):
        mock_dispatch.return_value = 0
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        code = main(
            [
                "--project", "test3",
                "--feature", "slug-gen",
                "--issue", "02",
                "--vm",
                "--memory", "2",
                "--model", "MiMo-V2.6-Flash",
                "--testing",
            ],
            stdout=stdout_buf,
            stderr=stderr_buf,
            repo_root=self.repo_root,
        )

        self.assertEqual(code, 0)
        mock_dispatch.assert_called_once_with(
            project="test3",
            feature="slug-gen",
            issue="02",
            vm=True,
            testing=True,
            model="mimo-v2.6-flash",
            memory_gb=2,
            stdout=stdout_buf,
            stderr=stderr_buf,
        )

    @patch("factory.run.dispatch_job")
    def test_main_propagates_non_zero_exit_code(self, mock_dispatch):
        mock_dispatch.return_value = 42
        code = main(
            ["--project", "test3", "--feature", "slug-gen", "--testing"],
            repo_root=self.repo_root,
        )
        self.assertEqual(code, 42)

    @patch("modal.enable_output")
    @patch("factory.run.dispatch_job")
    def test_main_enables_modal_output(self, mock_dispatch, mock_enable_output):
        mock_dispatch.return_value = 0
        mock_cm = MagicMock()
        mock_enable_output.return_value = mock_cm

        code = main(
            ["--project", "test3", "--feature", "slug-gen", "--testing"],
            repo_root=self.repo_root,
        )

        self.assertEqual(code, 0)
        mock_enable_output.assert_called_once()
        mock_cm.__enter__.assert_called_once()
        mock_cm.__exit__.assert_called_once()

    def test_cli_subprocess_help(self):
        proc = subprocess.run(
            ["python3", "factory/run.py", "--help"],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Launch an autonomous software factory assembly line", proc.stdout)

    def test_cli_direct_execution_help(self):
        proc = subprocess.run(
            ["./factory/run.py", "--help"],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("Launch an autonomous software factory assembly line", proc.stdout)

    def test_cli_subprocess_missing_secret(self):
        proc = subprocess.run(
            ["python3", "factory/run.py", "--project", "nonexistent-repo", "--feature", "feat1"],
            cwd=str(self.repo_root),
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("Target project secrets directory not found", proc.stderr)



if __name__ == "__main__":
    unittest.main()



