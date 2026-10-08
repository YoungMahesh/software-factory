import io
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

import factory
from factory.orchestrator import dispatch_job


class TestFactoryOrchestrator(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parent.parent

    def test_factory_reexports(self):
        self.assertTrue(hasattr(factory, "create_factory_sandbox"))
        self.assertTrue(hasattr(factory, "spawn_factory_sandbox"))
        self.assertTrue(hasattr(factory, "run_factory_sandbox"))
        self.assertTrue(hasattr(factory, "build_factory_image"))
        self.assertTrue(hasattr(factory, "FactorySpawnConfig"))
        self.assertTrue(hasattr(factory, "dispatch_job"))
        self.assertTrue(hasattr(factory, "run_cli"))
        self.assertTrue(hasattr(factory, "main"))
        self.assertTrue(hasattr(factory, "validate_project_secrets"))


    @patch("factory.orchestrator.run_factory_sandbox")
    def test_dispatch_job(self, mock_run):
        mock_run.return_value = 0
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()

        code = dispatch_job(
            project="test3",
            feature="slug-generator",
            issue="02",
            testing=True,
            vm=True,
            model="mimo",
            memory_gb=2,
            stdout=stdout_buf,
            stderr=stderr_buf,
        )

        self.assertEqual(code, 0)
        mock_run.assert_called_once()
        config = mock_run.call_args[0][0]
        self.assertEqual(config.project, "test3")
        self.assertEqual(config.feature, "slug-generator")
        self.assertEqual(config.issue, "02")
        self.assertTrue(config.testing)
        self.assertTrue(config.vm)
        self.assertEqual(config.model, "mimo")
        self.assertEqual(config.memory_gb, 2)


if __name__ == "__main__":
    unittest.main()
