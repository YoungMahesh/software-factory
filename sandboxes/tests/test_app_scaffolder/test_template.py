"""Tests for App Template materialization, overlays, mobile identifiers, and workspace safety."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from sandbox.app_scaffolder import AppScaffoldRequest, sanitize_identifiers, scaffold_app


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class TestAppScaffolderTemplate(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)
        self.factory_root = _repo_root()
        self.template_dir = self.factory_root / "app-template"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sanitize_identifiers(self):
        self.assertEqual(sanitize_identifiers("My Cool App!"), ("my-cool-app", "mycoolapp", "com.app.mycoolapp"))
        self.assertEqual(sanitize_identifiers("123app"), ("123app", "app123app", "com.app.app123app"))

    def test_minimal_web_only_scaffold(self):
        target = self.tmp_path / "minimal-web"
        res = scaffold_app(
            AppScaffoldRequest(
                project_name="minimal-web",
                project_dir=target,
                mobile_app=False,
                db=False,
                auth=False,
                skills=False,
                install=False,
                git=False,
                template_dir=self.template_dir,
            )
        )

        self.assertEqual(res.project_name, "minimal-web")
        root_pkg = json.loads((target / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(root_pkg["name"], "minimal-web")
        self.assertNotIn("mobile", root_pkg["scripts"])
        self.assertNotIn("skills:update", root_pkg["scripts"])

        self.assertTrue((target / "apps" / "web" / "lib" / "env.ts").is_file())
        self.assertTrue((target / "apps" / "web" / "next.config.ts").is_file())
        self.assertIn("loadWorkspaceEnv()", (target / "apps" / "web" / "next.config.ts").read_text(encoding="utf-8"))
        self.assertFalse((target / "apps" / "mobile").exists())
        self.assertFalse((target / "apps" / "web" / "db").exists())
        self.assertFalse((target / "apps" / "web" / "lib" / "auth.ts").exists())
        self.assertFalse((target / ".agents").exists())

        web_pkg = json.loads((target / "apps" / "web" / "package.json").read_text(encoding="utf-8"))
        self.assertNotIn("drizzle-orm", web_pkg["dependencies"])
        self.assertNotIn("better-auth", web_pkg["dependencies"])
        self.assertNotIn("DATABASE_URL", (target / ".env").read_text(encoding="utf-8"))

    def test_full_stack_scaffold_with_mobile_db_auth_and_random_secret(self):
        target = self.tmp_path / "Full-Stack-App"
        scaffold_app(
            AppScaffoldRequest(
                project_name="Full-Stack-App",
                project_dir=target,
                mobile_app=True,
                db=True,
                auth=True,
                skills=True,
                install=False,
                git=False,
                template_dir=self.template_dir,
                skills_source_dir=self.factory_root,
            )
        )

        root_pkg = json.loads((target / "package.json").read_text(encoding="utf-8"))
        self.assertEqual(root_pkg["name"], "Full-Stack-App")
        self.assertIn("mobile", root_pkg["scripts"])
        self.assertIn("skills:update", root_pkg["scripts"])

        web_pkg = json.loads((target / "apps" / "web" / "package.json").read_text(encoding="utf-8"))
        self.assertIn("drizzle-orm", web_pkg["dependencies"])
        self.assertIn("pg", web_pkg["dependencies"])
        self.assertIn("better-auth", web_pkg["dependencies"])
        self.assertEqual(web_pkg["scripts"]["db:migrate"], "drizzle-kit migrate")

        # Portable TLS and monorepo .env support
        db_cfg = (target / "apps" / "web" / "db" / "config.ts").read_text(encoding="utf-8")
        self.assertIn("findFallbackCaCert", db_cfg)
        self.assertIn(".config", db_cfg)
        self.assertIn("resource-plane", db_cfg)
        self.assertIn("resolveDatabaseConfig", (target / "apps" / "web" / "db" / "index.ts").read_text(encoding="utf-8"))
        self.assertIn("resolveDatabaseConfig", (target / "apps" / "web" / "drizzle.config.ts").read_text(encoding="utf-8"))

        # Random auth secret generated rather than static placeholder
        env_text = (target / ".env").read_text(encoding="utf-8")
        self.assertIn("DATABASE_URL=", env_text)
        self.assertIn("BETTER_AUTH_SECRET=", env_text)
        self.assertNotIn("development-insecure-secret-key-32chars!!", env_text)
        self.assertNotIn("replace-with-32-char-random-secret", env_text)
        self.assertEqual((target / ".env").stat().st_mode & 0o777, 0o600)

        # Parameterized mobile identifiers
        app_json = json.loads((target / "apps" / "mobile" / "app.json").read_text(encoding="utf-8"))
        self.assertEqual(app_json["expo"]["name"], "Full-Stack-App")
        self.assertEqual(app_json["expo"]["slug"], "full-stack-app")
        self.assertEqual(app_json["expo"]["scheme"], "fullstackapp")
        self.assertEqual(app_json["expo"]["ios"]["bundleIdentifier"], "com.app.fullstackapp")
        self.assertEqual(app_json["expo"]["android"]["package"], "com.app.fullstackapp")

        mobile_pkg = json.loads((target / "apps" / "mobile" / "package.json").read_text(encoding="utf-8"))
        self.assertIn("expo-secure-store", mobile_pkg["dependencies"])

        if shutil.which("node"):
            serve_apk = target / "apps" / "mobile" / "scripts" / "serve-apk.js"
            proc = subprocess.run(
                [
                    "node",
                    "-e",
                    f"const m = require({json.dumps(str(serve_apk))}); console.log(JSON.stringify(m.loadMobileAppMeta({json.dumps(str(target / 'apps' / 'mobile'))})));",
                ],
                capture_output=True,
                text=True,
                check=True,
            )
            meta = json.loads(proc.stdout.strip())
            self.assertEqual(meta["name"], "Full-Stack-App")
            self.assertEqual(meta["slug"], "full-stack-app")
            self.assertEqual(meta["basePackageId"], "com.app.fullstackapp")

    def test_existing_standalone_sandbox_workspace_merges_gitignore_and_preserves_git(self):
        target = self.tmp_path / "sandbox-app"
        target.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(target)], capture_output=True, check=True)
        (target / ".gitignore").write_text(".env\n.venv/\nmy-custom-ignore/\n", encoding="utf-8")
        git_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Tester",
            "GIT_AUTHOR_EMAIL": "tester@example.com",
            "GIT_COMMITTER_NAME": "Tester",
            "GIT_COMMITTER_EMAIL": "tester@example.com",
        }
        subprocess.run(["git", "-C", str(target), "add", ".gitignore"], check=True, env=git_env)
        subprocess.run(["git", "-C", str(target), "commit", "-m", "initial commit"], check=True, env=git_env)

        with unittest.mock.patch.dict(os.environ, git_env):
            res = scaffold_app(
                AppScaffoldRequest(
                    project_name="sandbox-app",
                    project_dir=target,
                    mobile_app=False,
                    db=False,
                    auth=False,
                    skills=False,
                    install=False,
                    git=True,
                    force=False,
                    template_dir=self.template_dir,
                )
            )

        self.assertTrue(res.reused_existing_git)
        self.assertTrue(res.git_committed)
        gitignore = (target / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("my-custom-ignore/", gitignore)
        self.assertIn("node_modules/", gitignore)
        log = subprocess.run(["git", "-C", str(target), "log", "--oneline"], capture_output=True, text=True, check=True)
        self.assertEqual(len(log.stdout.strip().splitlines()), 2)

    def test_non_empty_directory_refused_without_force_and_allowed_with_force(self):
        target = self.tmp_path / "existing"
        target.mkdir()
        (target / "README.md").write_text("existing content", encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            scaffold_app(
                AppScaffoldRequest(
                    project_name="existing",
                    project_dir=target,
                    skills=False,
                    install=False,
                    git=False,
                    force=False,
                    template_dir=self.template_dir,
                )
            )
        self.assertIn("--force", str(ctx.exception))

        res = scaffold_app(
            AppScaffoldRequest(
                project_name="existing",
                project_dir=target,
                skills=False,
                install=False,
                git=False,
                force=True,
                template_dir=self.template_dir,
            )
        )
        self.assertTrue((res.project_dir / "apps" / "web" / "package.json").is_file())
