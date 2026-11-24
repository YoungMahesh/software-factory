"""Launch tests must never reserve profiles in a configured Modal workspace."""

from unittest.mock import MagicMock, patch

from sandbox.core import LaunchRequest
from sandbox.launcher import SandboxLauncher


def test_launch_tests_cannot_reserve_a_configured_codex_profile(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("CODEX_PROFILE_VOLUME_PREFIX=operator-pool\n")
    monkeypatch.setenv("CODEX_PROFILE_VOLUME_PREFIX", "operator-pool")
    sandbox = MagicMock()
    sandbox.object_id = "sb-unit-test"
    sandbox.poll.return_value = None
    sandbox.tunnels.return_value = {}
    launcher = SandboxLauncher(
        repo_root=tmp_path,
        build_image_fn=MagicMock(),
        load_pubkey_fn=lambda: "ssh-ed25519 fixture",
        resolve_git_identity_fn=lambda: {},
        resolve_provenance_fn=lambda root: {},
    )
    with (
        patch("modal.App.lookup"),
        patch("modal.Sandbox.create", return_value=sandbox),
        patch("sandbox.lifecycle.record_sandbox_connection_info"),
        patch("sandbox.codex_profiles.select_profile", return_value=None) as select,
    ):
        running = launcher.launch(LaunchRequest(name="fixture", t3=True, no_t3_persist=True))

    select.assert_not_called()
    assert running.response.codex_profile is None
