"""Codex credential profile selection and credential-free status tests."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from sandbox import codex_profiles
from sandbox.web import create_app


def test_prefers_available_saved_profile():
    profiles = [
        codex_profiles.Profile("A", MagicMock(), False, "available", None),
        codex_profiles.Profile("B", MagicMock(), True, "in use", "other-sandbox"),
        codex_profiles.Profile("C", MagicMock(), True, "available", None),
    ]
    with patch.object(codex_profiles, "list_profiles", return_value=profiles):
        assert codex_profiles.select_profile("prefix", None) is profiles[2]


def test_records_owner_before_mounting_only_codex_home():
    volume = MagicMock()
    upload = volume.batch_upload.return_value.__enter__.return_value
    profile = codex_profiles.Profile("A", volume, True, "available", None)
    env, mounts, tags = {}, {}, {"app_name": "repo", "instance_name": "repo-123"}
    profile.attach(env, mounts, tags)

    args = upload.put_file.call_args.args
    assert json.load(args[0]) == {"name": "repo-123", "app": "repo", "id": None}
    assert args[1] == "/owner.json"
    assert env == {"CODEX_HOME": codex_profiles.CODEX_HOME, "CODEX_PROFILE": "A"}
    volume.with_mount_options.assert_called_once_with(sub_path="/codex-home")
    assert mounts[codex_profiles.CODEX_HOME] is volume.with_mount_options.return_value


def test_pending_owner_is_reusable_only_after_matching_sandbox_exits():
    volume = MagicMock()
    volume.read_file.return_value = [b'{"name":"repo-123","app":"repo","id":null}']
    with patch("modal.Sandbox.from_name") as lookup:
        sandbox = lookup.return_value
        sandbox.get_tags.return_value = {}
        sandbox.poll.return_value = 0
        assert codex_profiles._owner_state(volume, None) == ("unknown", "repo-123")

        sandbox.get_tags.return_value = {"codex_attempt": "repo-123"}
        sandbox.poll.return_value = None
        assert codex_profiles._owner_state(volume, None) == ("in use", "repo-123")
        sandbox.poll.return_value = 0
        assert codex_profiles._owner_state(volume, None) == ("available", None)


def test_profile_status_uses_signed_scope(monkeypatch):
    monkeypatch.setenv("CODEX_PROFILE_VOLUME_PREFIX", "profiles")
    monkeypatch.setenv("CODEX_STATUS_SECRET", "test-signing-key")
    settings = codex_profiles.status_access(
        "https://factory.example", "test-signing-key", None, True, 60,
    )
    result = [{"profile": "A", "saved_login": True, "state": "available", "sandbox": None}]
    with patch.object(codex_profiles, "list_profiles", return_value=[SimpleNamespace(status=lambda: result[0])]) as read:
        with TestClient(create_app()) as client:
            assert client.get(codex_profiles.STATUS_PATH).status_code == 401
            response = client.get(codex_profiles.STATUS_PATH, headers={
                "Authorization": f"Bearer {settings['CODEX_STATUS_TOKEN']}",
            })
    assert response.json() == result
    read.assert_called_once_with("test-profiles", None)


def test_empty_created_modal_volume_is_available():
    volume = MagicMock()
    volume.listdir.side_effect = codex_profiles.modal.exception.NotFoundError("missing auth file")
    volume.read_file.side_effect = FileNotFoundError
    with patch("modal.Volume.from_name", return_value=volume):
        profiles = codex_profiles.list_profiles("prefix", create=True)
    assert all(entry.state == "available" and not entry.saved_login for entry in profiles)
