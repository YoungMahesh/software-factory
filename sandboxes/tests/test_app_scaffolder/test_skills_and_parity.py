"""Tests for App Template skills allowlist, lockfile parity, and @repo/theme token parity."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from sandbox.app_scaffolder import AppScaffoldRequest, load_skills_manifest, scaffold_app


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


class TestSkillsAllowlistAndParity(unittest.TestCase):
    def setUp(self):
        self.factory_root = _repo_root()
        self.template_dir = self.factory_root / "app-template"

    def test_skills_manifest_matches_root_lockfile_and_excludes_factory_skills(self):
        manifest = load_skills_manifest(self.template_dir)
        lock_data = json.loads((self.factory_root / "skills-lock.json").read_text(encoding="utf-8"))
        locked_skills = lock_data["skills"]

        self.assertEqual(manifest["source"], "mattpocock/skills")
        self.assertNotIn("modal", manifest["skills"])
        self.assertNotIn("close-modal-sandboxes", manifest["skills"])

        for skill_name in manifest["skills"]:
            self.assertIn(skill_name, locked_skills, f"Allowlisted skill {skill_name} missing from skills-lock.json")
            entry = locked_skills[skill_name]
            self.assertEqual(entry.get("source"), manifest["source"])
            self.assertEqual(entry.get("commit"), manifest["commit"])
            self.assertTrue((self.factory_root / ".agents" / "skills" / skill_name).is_dir())

    def test_scaffold_copies_only_allowlisted_skills_and_filters_lockfile(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            fake_source = tmp / "source"
            shutil.copytree(self.factory_root / ".agents", fake_source / ".agents")
            shutil.copytree(self.factory_root / "docs" / "agents", fake_source / "docs" / "agents")
            shutil.copy2(self.factory_root / "skills-lock.json", fake_source / "skills-lock.json")

            # Add an extra custom non-mattpocock skill to simulate future custom additions
            custom_skill = fake_source / ".agents" / "skills" / "custom-internal-skill"
            custom_skill.mkdir(parents=True)
            (custom_skill / "SKILL.md").write_text("---\nname: custom-internal-skill\n---\n", encoding="utf-8")

            target = tmp / "my-app"
            scaffold_app(
                AppScaffoldRequest(
                    project_name="my-app",
                    project_dir=target,
                    mobile_app=False,
                    db=False,
                    auth=False,
                    skills=True,
                    install=False,
                    git=False,
                    template_dir=self.template_dir,
                    skills_source_dir=fake_source,
                )
            )

            manifest = load_skills_manifest(self.template_dir)
            copied_skills = sorted(p.name for p in (target / ".agents" / "skills").iterdir() if p.is_dir())
            self.assertEqual(copied_skills, sorted(manifest["skills"]))
            self.assertNotIn("modal", copied_skills)
            self.assertNotIn("close-modal-sandboxes", copied_skills)
            self.assertNotIn("custom-internal-skill", copied_skills)

            generated_lock = json.loads((target / "skills-lock.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(generated_lock["skills"].keys()), sorted(manifest["skills"]))
            self.assertTrue((target / "AGENTS.md").is_file())
            self.assertTrue((target / "GLOSSARY.md").is_file())
            for doc in manifest["agentDocs"]:
                self.assertTrue((target / "docs" / "agents" / doc).is_file())

    def test_theme_tokens_match_resource_plane_theme(self):
        app_theme = self.template_dir / "packages" / "theme" / "src"
        rp_theme = self.factory_root / "resource-plane" / "packages" / "theme" / "src"
        for filename in ("colors.ts", "radii.ts", "spacing.ts", "typography.ts"):
            self.assertEqual(
                (app_theme / filename).read_text(encoding="utf-8"),
                (rp_theme / filename).read_text(encoding="utf-8"),
                f"Theme token file {filename} drifted from resource-plane/packages/theme/src/{filename}",
            )

    def test_no_repohorizon_branding_remains_in_app_template(self):
        for file_path in self.template_dir.rglob("*"):
            if not file_path.is_file() or file_path.suffix == ".png":
                continue
            content = file_path.read_text(encoding="utf-8", errors="ignore").lower()
            self.assertNotIn("repohorizon", content, f"Found leftover RepoHorizon string in {file_path}")
