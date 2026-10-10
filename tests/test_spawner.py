import io
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

from factory.spawner import (
    FACTORY_CPU,
    FACTORY_IDLE_TIMEOUT_SECS,
    FACTORY_STANDARD_MEMORY,
    FACTORY_TIMEOUT_SECS,
    FACTORY_VM_DEFAULT_MEMORY_GB,
    FactorySpawnConfig,
    build_factory_image,
    create_factory_sandbox,
    get_factory_app_name,
    resolve_secrets_dir,
    run_factory_sandbox,
    spawn_factory_sandbox,
    stream_sandbox_logs,
)


class TestFactorySpawner(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent

    def test_timeout_constants(self):
        self.assertEqual(FACTORY_TIMEOUT_SECS, 16 * 60 * 60)
        self.assertEqual(FACTORY_IDLE_TIMEOUT_SECS, 4 * 60 * 60)
        self.assertEqual(FACTORY_STANDARD_MEMORY, (128, 16384))
        self.assertEqual(FACTORY_VM_DEFAULT_MEMORY_GB, 1)
        self.assertEqual(FACTORY_CPU, (0.125, 4.0))

    def test_resolve_secrets_dir_production(self):
        # software-factory or repo-horizon exists in secrets/
        secrets_dir = resolve_secrets_dir("software-factory", testing=False, repo_root=self.repo_root)
        self.assertTrue(secrets_dir.is_dir())
        self.assertTrue((secrets_dir / "fetch.env").is_file())
        self.assertIn("secrets/software-factory", str(secrets_dir))

    def test_resolve_secrets_dir_testing(self):
        # test3 targets software-factory-09-test in secrets_org/
        secrets_dir = resolve_secrets_dir("test3", testing=True, repo_root=self.repo_root)
        self.assertTrue(secrets_dir.is_dir())
        self.assertTrue((secrets_dir / "token").is_file())
        self.assertIn("secrets_org/software-factory-09-test", str(secrets_dir))

    def test_resolve_secrets_dir_prefixed_inputs(self):
        # 'secrets/software-factory' should resolve without duplication
        dir1 = resolve_secrets_dir("secrets/software-factory", repo_root=self.repo_root)
        self.assertTrue((dir1 / "fetch.env").is_file())
        self.assertIn("secrets/software-factory", str(dir1))

        # 'software-factory-09-test/test3' should automatically resolve under secrets_org
        dir2 = resolve_secrets_dir("software-factory-09-test/test3", repo_root=self.repo_root)
        self.assertTrue((dir2 / "token").is_file())
        self.assertIn("secrets_org/software-factory-09-test", str(dir2))

    def test_get_factory_app_name_prefixed(self):
        app1 = get_factory_app_name("secrets/software-factory")
        self.assertNotIn("/", app1)
        self.assertIn("software-factory", app1)
        self.assertFalse(app1.startswith("test-"))

        app2 = get_factory_app_name("software-factory-09-test/test3")
        self.assertNotIn("/", app2)
        self.assertIn("test3", app2)
        self.assertTrue(app2.startswith("test-"))

    def test_resolve_secrets_dir_missing_project(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            resolve_secrets_dir("nonexistent-proj", testing=False, repo_root=self.repo_root)
        self.assertIn("nonexistent-proj", str(ctx.exception))

    def test_get_factory_app_name(self):
        prod_name = get_factory_app_name("my-project", testing=False)
        self.assertFalse(prod_name.startswith("test-"))
        self.assertIn("my-project", prod_name)

        test_name = get_factory_app_name("my-project", testing=True)
        self.assertTrue(test_name.startswith("test-"))
        self.assertIn("my-project", test_name)

    def test_build_factory_image(self):
        proj_secrets_dir = self.repo_root / "secrets_org" / "software-factory-09-test"
        factory_dir = self.repo_root / "sandbox" / "factory"
        image = build_factory_image(
            project_secrets_dir=proj_secrets_dir,
            factory_dir=factory_dir,
            repo_root=self.repo_root,
        )
        self.assertIsNotNone(image)

    @patch("modal.App.lookup")
    @patch("modal.Sandbox.create")
    def test_create_factory_sandbox_standard(self, mock_sandbox_create, mock_app_lookup):
        mock_app = MagicMock()
        mock_app_lookup.return_value = mock_app
        mock_sandbox = MagicMock()
        mock_sandbox_create.return_value = mock_sandbox

        config = FactorySpawnConfig(
            project="test3",
            feature="slug-generator",
            issue="01",
            testing=True,
            vm=False,
            model="mimo",
            repo_root=self.repo_root,
        )

        sandbox = create_factory_sandbox(config)
        self.assertEqual(sandbox, mock_sandbox)

        mock_app_lookup.assert_called_once()
        app_name_arg = mock_app_lookup.call_args[0][0]
        self.assertTrue(app_name_arg.startswith("test-"))

        mock_sandbox_create.assert_called_once()
        args, kwargs = mock_sandbox_create.call_args

        self.assertEqual(args[0], "bash")
        self.assertEqual(args[1], "/root/factory_entrypoint.sh")
        self.assertIn("--feature", args)
        self.assertIn("slug-generator", args)
        self.assertIn("--issue", args)
        self.assertIn("01", args)
        self.assertIn("--model", args)
        self.assertIn("mimo", args)

        self.assertEqual(kwargs["timeout"], FACTORY_TIMEOUT_SECS)
        self.assertEqual(kwargs["idle_timeout"], FACTORY_IDLE_TIMEOUT_SECS)
        self.assertEqual(kwargs["memory"], FACTORY_STANDARD_MEMORY)
        self.assertEqual(kwargs["cpu"], FACTORY_CPU)
        self.assertNotIn("experimental_options", kwargs)

        # Check share0 secret
        secrets = kwargs["secrets"]
        self.assertEqual(len(secrets), 1)

        # Check env
        env = kwargs["env"]
        self.assertEqual(env["FEATURE_SLUG"], "slug-generator")
        self.assertEqual(env["ENABLE_DOCKER"], "0")

    @patch("modal.App.lookup")
    @patch("modal.Sandbox.create")
    def test_create_factory_sandbox_vm(self, mock_sandbox_create, mock_app_lookup):
        mock_app = MagicMock()
        mock_app_lookup.return_value = mock_app
        mock_sandbox = MagicMock()
        mock_sandbox_create.return_value = mock_sandbox

        config = FactorySpawnConfig(
            project="software-factory",
            feature="autonomous-worker",
            testing=False,
            vm=True,
            memory_gb=2,
            repo_root=self.repo_root,
        )

        sandbox = create_factory_sandbox(config)
        self.assertEqual(sandbox, mock_sandbox)

        mock_app_lookup.assert_called_once()
        app_name_arg = mock_app_lookup.call_args[0][0]
        self.assertFalse(app_name_arg.startswith("test-"))

        mock_sandbox_create.assert_called_once()
        args, kwargs = mock_sandbox_create.call_args

        # No issue or model passed
        self.assertIn("--feature", args)
        self.assertNotIn("--issue", args)
        self.assertNotIn("--model", args)

        # VM configuration: memory in MiB (2 * 1024), vm_runtime True
        self.assertEqual(kwargs["memory"], 2048)
        self.assertEqual(kwargs["experimental_options"], {"vm_runtime": True})

        env = kwargs["env"]
        self.assertEqual(env["ENABLE_DOCKER"], "1")
        self.assertEqual(env["SWAP_GB"], "4")

    @patch("modal.App.lookup")
    @patch("modal.Sandbox.create")
    def test_create_factory_sandbox_with_dev_preview(self, mock_sandbox_create, mock_app_lookup):
        mock_app = MagicMock()
        mock_app_lookup.return_value = mock_app
        mock_sandbox = MagicMock()
        mock_sandbox_create.return_value = mock_sandbox

        config = FactorySpawnConfig(
            project="test3",
            feature="preview-app",
            testing=True,
            dev=True,
            repo_root=self.repo_root,
        )

        sandbox = create_factory_sandbox(config)
        self.assertEqual(sandbox, mock_sandbox)

        mock_sandbox_create.assert_called_once()
        args, kwargs = mock_sandbox_create.call_args

        self.assertIn("--dev", args)
        env = kwargs["env"]
        self.assertEqual(env["DEV_PREVIEW"], "1")
        self.assertEqual(env["ENABLE_CLOUDFLARE"], "1")
        self.assertEqual(env["PORT"], "3000")

        # Emergency cancellation test via sandbox.terminate()
        sandbox.terminate()
        mock_sandbox.terminate.assert_called_once()

    @patch("factory.spawner.create_factory_sandbox")
    def test_spawn_factory_sandbox_alias(self, mock_create):
        mock_sandbox = MagicMock()
        mock_create.return_value = mock_sandbox
        config = FactorySpawnConfig(project="test3", feature="test-feat", testing=True, repo_root=self.repo_root)
        res = spawn_factory_sandbox(config)
        self.assertEqual(res, mock_sandbox)
        mock_create.assert_called_once_with(config)

    def test_stream_sandbox_logs(self):
        mock_sandbox = MagicMock()
        mock_sandbox.stdout = ["line 1\n", "line 2\n"]
        mock_sandbox.stderr = ["warning 1\n"]
        mock_sandbox.wait.return_value = None
        mock_sandbox.returncode = 0

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        code = stream_sandbox_logs(mock_sandbox, stdout=stdout_buf, stderr=stderr_buf)
        self.assertEqual(code, 0)
        self.assertEqual(stdout_buf.getvalue(), "line 1\nline 2\n")
        self.assertEqual(stderr_buf.getvalue(), "warning 1\n")

    @patch("factory.spawner.stream_sandbox_logs")
    @patch("factory.spawner.create_factory_sandbox")
    def test_run_factory_sandbox(self, mock_create, mock_stream):
        mock_sandbox = MagicMock()
        mock_create.return_value = mock_sandbox
        mock_stream.return_value = 42

        config = FactorySpawnConfig(project="test3", feature="test-feat", repo_root=self.repo_root)
        code = run_factory_sandbox(config)
        self.assertEqual(code, 42)
        mock_create.assert_called_once_with(config)
        mock_stream.assert_called_once_with(mock_sandbox, stdout=unittest.mock.ANY, stderr=unittest.mock.ANY)


if __name__ == "__main__":
    unittest.main()
