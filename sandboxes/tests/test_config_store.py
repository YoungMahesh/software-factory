"""Central Config Store behavior through its repository interface and HTTP adapter."""

import base64
import io
import json
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from unittest.mock import patch

import pytest

from sandbox.config_store import CentralConfigStore, ConfigStoreError, ConfigStoreHTTPError, github_json_request


class GitHubMemory:
    """Mock external dependency, preserving GitHub create/update/delete preconditions."""

    def __init__(self):
        self.files = {}
        self.calls = []
        self.sequence = 0

    def __call__(self, url, token, *, method="GET", payload=None):
        self.calls.append((url, token, method, payload))
        path = unquote(urlparse(url).path).split("/contents/", 1)[-1]
        if "/git/trees/" in url:
            return 200, {"tree": [{"type": "blob", "path": p, "sha": v[0]} for p, v in self.files.items()]}
        current = self.files.get(path)
        if method == "GET":
            if current:
                return 200, self.metadata(path)
            entries = [self.metadata(p) for p in self.files if p.startswith(path + "/")]
            return (200, entries) if entries else (404, {"message": "Not Found"})
        if method == "PUT":
            if current and payload.get("sha") != current[0]:
                return (409 if "sha" in payload else 422), {"message": "sha wasn't supplied or did not match"}
            if not current and "sha" in payload:
                return 409, {"message": "File does not exist"}
            self.sequence += 1
            self.files[path] = (f"version-{self.sequence}", base64.b64decode(payload["content"]))
            return (200 if current else 201), {"content": self.metadata(path), "commit": {"sha": f"commit-{self.sequence}"}}
        if method == "DELETE":
            if current is None or payload["sha"] != current[0]:
                return 409, {"message": "SHA mismatch"}
            del self.files[path]
            return 200, {}
        raise AssertionError(method)

    def metadata(self, path):
        sha, data = self.files[path]
        return {"type": "file", "name": path.rsplit("/", 1)[-1], "path": path, "sha": sha,
                "content": base64.b64encode(data).decode(), "encoding": "base64", "size": len(data)}

    def urlopen(self, request, *, timeout):
        assert timeout == 20
        assert request.get_header("Authorization") == "Bearer test-token"
        assert request.get_header("Cache-control") == "no-cache, max-age=0"
        status, body = self(request.full_url, "test-token", method=request.get_method(),
                            payload=json.loads(request.data) if request.data else None)
        stream = io.BytesIO(json.dumps(body).encode())
        if status >= 400:
            raise HTTPError(request.full_url, status, "GitHub error", {}, stream)
        stream.status = status
        return stream


def test_missing_file_differs_from_empty_file_and_update_preserves_versions():
    remote = GitHubMemory()
    store = CentralConfigStore("owner", "token", request=remote)
    assert store.read("env/project/default.env") is None
    created = store.write("env/project/default.env", b"", "create")
    assert store.read(created.path).content == b""
    updated = store.upsert(created.path, b"secret", "update")
    assert updated.sha != created.sha
    assert store.read(created.path).content == b"secret"
    assert remote.calls[-2][3]["sha"] == created.sha


def test_stale_update_and_delete_fail_without_retry_or_overwriting_newer_data():
    remote = GitHubMemory()
    store = CentralConfigStore("owner", "token", request=remote)
    first = store.write("caddy/prod/conf/Caddyfile", b"old", "create")
    store.write(first.path, b"new", "update", expected_sha=first.sha)
    before = len(remote.calls)
    with pytest.raises(ConfigStoreHTTPError) as error:
        store.write(first.path, b"stale", "update", expected_sha=first.sha)
    assert error.value.status == 409
    assert len(remote.calls) == before + 1
    with pytest.raises(ConfigStoreHTTPError):
        store.delete(first.path, first.sha, "remove")
    assert store.read(first.path).content == b"new"
    with pytest.raises(ValueError):
        store.delete(first.path, "", "remove")
    store.delete(first.path, store.read(first.path).sha, "remove")
    assert store.read(first.path) is None


def test_create_only_write_never_overwrites_an_existing_note():
    remote = GitHubMemory()
    store = CentralConfigStore("owner", "token", request=remote)
    store.write("scratchpad/idea.md", b"first", "create")
    with pytest.raises(ConfigStoreHTTPError) as error:
        store.write("scratchpad/idea.md", b"second", "create")
    assert error.value.creation_collision
    assert store.read("scratchpad/idea.md").content == b"first"
    assert not ConfigStoreHTTPError(422, {"message": "Validation failed"}, "x").creation_collision


@pytest.mark.parametrize("error", [TimeoutError(), URLError("offline"), ValueError("bad JSON")])
def test_transport_failure_is_not_absence_and_cannot_trigger_a_write(error):
    with patch("urllib.request.urlopen", side_effect=error) as send:
        with pytest.raises(ConfigStoreError):
            CentralConfigStore("owner", "token").upsert("env/p/default.env", b"data", "write")
        assert send.call_count == 1


@pytest.mark.parametrize("body", [{"content": "%%%"}, {"content": "x", "encoding": "none"}, []])
def test_malformed_content_is_not_missing(body):
    store = CentralConfigStore("owner", "token", request=lambda *args, **kwargs: (200, body))
    with pytest.raises(ConfigStoreError):
        store.read("env/p/default.env")


def test_unreadable_or_truncated_catalog_cannot_be_used_to_infer_deletions():
    with pytest.raises(ConfigStoreHTTPError) as error:
        CentralConfigStore("owner", "token", request=lambda *a, **k: (403, {"message": "Forbidden"})).list_directory("scratchpad")
    assert error.value.status == 403
    for body in [{"tree": [], "truncated": True}, {"tree": "wrong"}]:
        with pytest.raises(ConfigStoreError):
            CentralConfigStore("owner", "token", request=lambda *a, **k: (200, body)).list_tree()


def test_paths_are_encoded_and_cannot_change_the_operation_target():
    remote = GitHubMemory()
    store = CentralConfigStore("owner", "token", request=remote)
    path = "env/project/file #?.env"
    store.write(path, b"data", "write")
    assert "%23%3F" in remote.calls[-1][0]
    assert store.read(path).content == b"data"
    for path in ["../other", "/absolute", "a//b", "a/./b", "a\\b", "a\0b"]:
        with pytest.raises(ValueError):
            store.read(path)


def test_malformed_json_and_http_error_details_are_consistent():
    stream = io.BytesIO(b"{invalid")
    stream.status = 200
    with patch("urllib.request.urlopen", return_value=stream):
        with pytest.raises(ConfigStoreError):
            github_json_request("https://api.github.com/repos/o/config", "token")
    response = HTTPError("https://api.github.com", 503, "error", {}, io.BytesIO(b"temporarily unavailable"))
    with patch("urllib.request.urlopen", side_effect=response):
        status, body = github_json_request("https://api.github.com/repos/o/config", "token")
        assert status == 503
        assert body == {"message": "temporarily unavailable"}


def test_all_three_domain_workflows_use_the_same_http_persistence_seam():
    from sandbox.env_store import fetch_github_file
    from sandbox.env_store_push import commit_to_env_store
    from sandbox.caddy_store import commit_caddy_store_file, fetch_caddy_store_bundle
    from sandbox.scratchpad import commit_scratchpad_note, read_scratchpad_note

    remote = GitHubMemory()
    with patch("urllib.request.urlopen", side_effect=remote.urlopen):
        # Encryption is supplied by the vault domain, never by persistence.
        commit_to_env_store("owner", "config", "env/project/default.env", b"ENC[encrypted]", "test-token")
        assert fetch_github_file("owner", "config", "env/project/default.env", "test-token") == "ENC[encrypted]"
        commit_caddy_store_file("owner", "caddy/prod/conf/Caddyfile", b"plain ingress", "test-token", "backup")
        # Filtering still belongs to Host Ingress Proxy backup, not repository transport.
        commit_caddy_store_file("owner", "caddy/prod/conf/file.tmp", b"transient", "test-token", "fixture")
        assert fetch_caddy_store_bundle("owner", "prod", "test-token") == {"conf/Caddyfile": "plain ingress"}
        saved = commit_scratchpad_note("owner", title="Idea", content="Body", token="test-token")
        second = commit_scratchpad_note("owner", title="Idea", content="Other", token="test-token")
        assert saved.filename == "idea.md"
        assert second.filename == "idea-2.md"
        assert read_scratchpad_note("owner", saved.filename, "test-token").content == "# Idea\n\nBody\n"
    assert all("/repos/owner/config/" in url for url, *_ in remote.calls)


def test_ingress_bundle_refuses_a_partial_read_when_a_listed_file_disappears():
    from sandbox.caddy_store import fetch_caddy_store_bundle

    remote = GitHubMemory()
    CentralConfigStore("owner", "test-token", request=remote).write("caddy/prod/conf/Caddyfile", b"data", "create")
    original = remote.urlopen

    def disappearing_file(request, **kwargs):
        if "/contents/" in request.full_url:
            remote.files.clear()
        return original(request, **kwargs)

    with patch("urllib.request.urlopen", side_effect=disappearing_file):
        with pytest.raises(ConfigStoreError, match="changed while reading"):
            fetch_caddy_store_bundle("owner", "prod", "test-token")


def test_malformed_write_success_is_reported_as_ambiguous_failure_without_retry():
    calls = []

    def request(*args, **kwargs):
        calls.append(kwargs)
        return 201, {}

    with pytest.raises(ConfigStoreError, match="Malformed commit response"):
        CentralConfigStore("owner", "token", request=request).write("env/p/default.env", b"data", "write")
    assert len(calls) == 1
