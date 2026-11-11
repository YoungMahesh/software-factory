"""Startup script and environment configuration tests for T3 Code integration."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class TestT3CodeStartup(unittest.TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.startup_sh = self.repo_root / "shared" / "startup.sh"

    def test_startup_script_contains_software_factory_provenance_and_check_script(self):
        content = self.startup_sh.read_text()
        for token in [
            "SOFTWARE_FACTORY_COMMIT",
            "SOFTWARE_FACTORY_COMMIT_SHORT",
            "SOFTWARE_FACTORY_REF",
            "SOFTWARE_FACTORY_DIRTY",
            "/etc/software-factory-version.json",
            "check-software-factory",
            "check-sf",
            "origin_commit",
            "resumed_commit",
            "https://github.com/${ORG}/${REPO}/compare/",
        ]:
            self.assertIn(token, content)

    def test_startup_script_contains_t3_daemon_and_check_script(self):
        content = self.startup_sh.read_text()
        for token in ["ENABLE_T3", "check-t3", "t3 serve", "GitHub CLI", "--auto-bootstrap-project-from-cwd"]:
            self.assertIn(token, content)

    def test_startup_script_contains_t3_usage_persistence_logic(self):
        content = self.startup_sh.read_text()
        self.assertIn("ENABLE_T3_PERSISTENCE", content)
        self.assertIn("t3-usage-sync hydrate", content)
        self.assertIn("t3-usage-sync daemon", content)
        self.assertIn("cleanup_t3", content)
        self.assertIn("trap cleanup_t3 EXIT SIGTERM", content)
        self.assertIn("ANTIGRAVITY_DATA_DIR", content)

    def test_startup_and_setup_scripts_contain_antigravity_preauth(self):
        startup_content = self.startup_sh.read_text()
        setup_content = (self.repo_root / "scripts" / "setup.sh").read_text()

        for content in [startup_content, setup_content]:
            self.assertIn("acp_token.json", content)
            self.assertIn("oauth-personal", content)
            self.assertIn("GOOGLE_CLIENT_ID", content)
            self.assertIn("providerInstances", content)
            self.assertIn("antigravity", content)
            self.assertIn("ANTIGRAVITY_TOKENS", content)
            self.assertIn("gemini-3.8-flash-high", content)
            self.assertNotIn("gemini-3.8-flash-medium", content)
            self.assertNotIn("Gemini 3.8 Flash (Low)", content)
            self.assertIn("sourceControlWriterModelSelection", content)
            self.assertIn("textGenerationModelSelection", content)
            self.assertIn("gemini-3.8-flash-low", content)
            self.assertIn("existing_tok", content)
            self.assertIn("candidate_file", content)

    def test_setup_script_configures_antigravity_from_env(self):
        setup_script = self.repo_root / "scripts" / "setup.sh"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            home_dir = tmp_path / "home"
            home_dir.mkdir()

            env = {
                "PATH": f"{bin_dir}:{os.environ.get('PATH', '/bin:/usr/bin')}",
                "HOME": str(home_dir),
                "ANTIGRAVITY_CLIENT_ID": "custom-client-id.apps.googleusercontent.com",
                "ANTIGRAVITY_CLIENT_SECRET": "custom-client-secret",
                "ANTIGRAVITY_TOKENS": '[{"name": "Personal", "token": "mock-refresh-token"}]',
            }
            res = subprocess.run(["bash", str(setup_script), "--t3"], capture_output=True, text=True, env=env)
            self.assertEqual(res.returncode, 0, f"setup.sh failed: {res.stderr}")

            acp_token_path = home_dir / ".gemini" / "antigravity-acp" / "acp_token.json"
            self.assertTrue(acp_token_path.exists(), "acp_token.json was not generated")
            acp_data = json.loads(acp_token_path.read_text())
            self.assertEqual(acp_data["client_id"], "custom-client-id.apps.googleusercontent.com")
            self.assertEqual(acp_data["client_secret"], "custom-client-secret")
            self.assertEqual(acp_data["refresh_token"], "mock-refresh-token")

            settings_path = home_dir / ".t3" / "userdata" / "settings.json"
            self.assertTrue(settings_path.exists(), "settings.json was not generated")
            settings_data = json.loads(settings_path.read_text())
            self.assertEqual(
                settings_data["sourceControlWriterModelSelection"],
                {"instanceId": "antigravity", "model": "gemini-3.8-flash-low"},
            )
            self.assertEqual(
                settings_data["textGenerationModelSelection"],
                {"instanceId": "antigravity", "model": "gemini-3.8-flash-low"},
            )

    def test_setup_script_prioritizes_first_antigravity_token_profile(self):
        setup_script = self.repo_root / "scripts" / "setup.sh"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            home_dir = tmp_path / "home"
            home_dir.mkdir()

            env = {
                "PATH": f"{bin_dir}:{os.environ.get('PATH', '/bin:/usr/bin')}",
                "HOME": str(home_dir),
                "ANTIGRAVITY_TOKENS": '[{"name": "ANV", "token": "anv-token"}, {"name": "MGH", "token": "mgh-token"}]',
            }
            res = subprocess.run(["bash", str(setup_script), "--t3"], capture_output=True, text=True, env=env)
            self.assertEqual(res.returncode, 0, f"setup.sh failed: {res.stderr}")

            settings_path = home_dir / ".t3" / "userdata" / "settings.json"
            self.assertTrue(settings_path.exists())
            settings_data = json.loads(settings_path.read_text())
            self.assertEqual(
                settings_data["sourceControlWriterModelSelection"],
                {"instanceId": "antigravity", "model": "gemini-3.8-flash-low"},
            )
            self.assertEqual(
                settings_data["textGenerationModelSelection"],
                {"instanceId": "antigravity", "model": "gemini-3.8-flash-low"},
            )
            self.assertIn("antigravity-mgh", settings_data["providerInstances"])
            self.assertEqual(settings_data["providerInstances"]["antigravity"]["displayName"], "ANV")
            self.assertEqual(settings_data["providerInstances"]["antigravity-mgh"]["displayName"], "MGH")

    def test_switch_agy_profile_offline_with_cached_profiles(self):
        agyprofile_script = self.repo_root / "scripts" / "agyprofile"
        switch_script = self.repo_root / "scripts" / "switch-agy-profile.sh"
        self.assertTrue(agyprofile_script.exists())
        self.assertTrue(switch_script.exists())

        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / ".gemini" / "antigravity-cli"
            profiles_dir = target_dir / "profiles"
            profiles_dir.mkdir(parents=True)
            (profiles_dir / "mgh").write_text('{"refresh_token": "token-mgh"}')
            (profiles_dir / "anv").write_text('{"refresh_token": "token-anv"}')
            (profiles_dir / "m47").write_text('{"refresh_token": "token-m47"}')

            env = {"TARGET_DIR": str(target_dir), "PATH": os.environ["PATH"]}
            res = subprocess.run(["bash", str(agyprofile_script), "mgh"], capture_output=True, text=True, env=env)
            self.assertEqual(res.returncode, 0, f"Failed: {res.stderr}")
            self.assertIn("Switched Antigravity CLI profile to: mgh", res.stdout)
            self.assertEqual((target_dir / "antigravity-oauth-token").read_text(), '{"refresh_token": "token-mgh"}')

            # Verify backwards compatibility symlink
            res_legacy = subprocess.run(["bash", str(switch_script), "anv"], capture_output=True, text=True, env=env)
            self.assertEqual(res_legacy.returncode, 0, f"Failed: {res_legacy.stderr}")
            self.assertIn("Switched Antigravity CLI profile to: anv", res_legacy.stdout)
            self.assertEqual((target_dir / "antigravity-oauth-token").read_text(), '{"refresh_token": "token-anv"}')

    def test_startup_and_setup_scripts_contain_opencode_preauth(self):
        startup_content = self.startup_sh.read_text()
        setup_content = (self.repo_root / "scripts" / "setup.sh").read_text()

        for content in [startup_content, setup_content]:
            self.assertIn("OPENCODE_GO_API_KEY", content)
            self.assertIn("providerInstances", content)
            self.assertIn("opencode", content)
            self.assertIn("/root/.opencode/bin/opencode", content)

    def test_startup_script_mints_pairing_token(self):
        content = self.startup_sh.read_text()
        self.assertIn("t3 auth pairing create --ttl 24h --json > /tmp/t3-pairing.json", content)

    def test_startup_script_installs_t3_wrapper_script(self):
        content = self.startup_sh.read_text()
        self.assertIn("cat << 'EOF' > /usr/local/bin/t3.wrapper", content)
        self.assertIn('REAL_T3="/opt/t3/t3"', content)
        self.assertIn('if [ "${1:-}" = "pair" ]; then', content)
        self.assertIn("devUrl", content)
        self.assertIn("/root/.t3/public_url", content)
        self.assertIn("chmod +x /usr/local/bin/t3.wrapper", content)

    def test_t3_wrapper_script_syncs_dev_url(self):
        content = self.startup_sh.read_text()
        start_marker = "cat << 'EOF' > /usr/local/bin/t3.wrapper\n"
        end_marker = "EOF\n    chmod +x /usr/local/bin/t3.wrapper"
        start_pos = content.find(start_marker) + len(start_marker)
        end_pos = content.find(end_marker, start_pos)
        wrapper_template = content[start_pos:end_pos]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            t3_dir = tmp_path / ".t3" / "userdata"
            t3_dir.mkdir(parents=True)
            runtime_json = t3_dir / "server-runtime.json"
            runtime_json.write_text(json.dumps({
                "version": 1,
                "pid": 1234,
                "origin": "http://127.0.0.1:3775",
                "port": 3775,
                "startedAt": "2026-10-28T00:00:00Z"
            }))

            public_url_file = tmp_path / ".t3" / "public_url"
            public_url_file.write_text("https://my-modal-url.modal.host\n")

            mock_bin = tmp_path / "mock_t3_bin"
            mock_bin.write_text('#!/usr/bin/env bash\necho "MOCK_CALLED: $@"\n')
            mock_bin.chmod(0o755)

            # Substitute paths for isolated sandbox test
            script = wrapper_template.replace("/root/.t3", str(tmp_path / ".t3"))
            script = script.replace('"/opt/t3/t3"', f'"{mock_bin}"')

            wrapper = tmp_path / "t3_wrapper"
            wrapper.write_text(script)
            wrapper.chmod(0o755)

            # Test non-pair command: server-runtime.json not modified
            res_serve = subprocess.run([str(wrapper), "serve"], capture_output=True, text=True)
            self.assertEqual(res_serve.returncode, 0)
            self.assertIn("MOCK_CALLED: serve", res_serve.stdout)
            data_after_serve = json.loads(runtime_json.read_text())
            self.assertNotIn("devUrl", data_after_serve)

            # Test pair command: devUrl is injected into server-runtime.json
            res_pair = subprocess.run([str(wrapper), "pair"], capture_output=True, text=True)
            self.assertEqual(res_pair.returncode, 0)
            self.assertIn("MOCK_CALLED: pair", res_pair.stdout)
            data_after_pair = json.loads(runtime_json.read_text())
            self.assertEqual(data_after_pair["devUrl"], "https://my-modal-url.modal.host")

    def test_startup_script_contains_t3_ssh_patch_and_machine_info(self):
        content = self.startup_sh.read_text()
        self.assertIn("t_ssh = base64.b64decode", content)
        self.assertIn("r_ssh = base64.b64decode", content)
        self.assertIn("new_c.replace(t_ssh, r_ssh, 1)", content)
        self.assertIn("PRETTY_HOSTNAME", content)

    def test_startup_script_scrubs_gh_repo_and_t3_wrapper_unsets_it(self):
        content = self.startup_sh.read_text()
        self.assertIn("unset GH_REPO", content)
        self.assertIn('grep -qxF "unset GH_REPO" ~/.bashrc', content)

        start_marker = "cat << 'EOF' > /usr/local/bin/t3.wrapper\n"
        end_marker = "EOF\n    chmod +x /usr/local/bin/t3.wrapper"
        start_pos = content.find(start_marker) + len(start_marker)
        end_pos = content.find(end_marker, start_pos)
        wrapper_template = content[start_pos:end_pos]
        self.assertIn("unset GH_REPO", wrapper_template)

    def test_setup_preserves_existing_acp_credentials_in_snapshot_resume(self):
        setup_script = self.repo_root / "scripts" / "setup.sh"
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            home_dir = tmp_path / "home"
            home_dir.mkdir()

            preseeded_dir = home_dir / ".gemini" / "antigravity-acp"
            preseeded_dir.mkdir(parents=True)
            preseeded_token = preseeded_dir / "acp_token.json"
            preseeded_token.write_text(json.dumps({
                "client_id": "persisted-snapshot-client-id.apps.googleusercontent.com",
                "client_secret": "persisted-snapshot-secret",
                "refresh_token": "stale-token",
                "project_id": "aicode-consumers"
            }))

            env = {
                "PATH": f"{bin_dir}:{os.environ.get('PATH', '/bin:/usr/bin')}",
                "HOME": str(home_dir),
                "ANTIGRAVITY_TOKENS": '[{"name": "Default", "token": "mock-refresh-token"}]',
            }
            res = subprocess.run(["bash", str(setup_script), "--t3"], capture_output=True, text=True, env=env)
            self.assertEqual(res.returncode, 0, f"setup.sh failed: {res.stderr}")

            acp_data = json.loads(preseeded_token.read_text())
            self.assertEqual(acp_data["client_id"], "persisted-snapshot-client-id.apps.googleusercontent.com")
            self.assertEqual(acp_data["client_secret"], "persisted-snapshot-secret")
            self.assertNotIn("project_id", acp_data)
            self.assertEqual(acp_data["refresh_token"], "mock-refresh-token")
