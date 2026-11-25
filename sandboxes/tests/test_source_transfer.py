"""Source transfer callers must reject partial archives and reap their processes."""

import shlex
import shutil
import subprocess
import sys

import pytest

from sandbox.app_deploy._deploy import sync_local_app_to_vps
from sandbox.infra_deploy import VpsSshConfig, sync_resource_plane_to_vps
from sandbox.source_transfer import stream_source_archive


@pytest.mark.parametrize("mode", ["resource-plane", "hosted-app"])
@pytest.mark.parametrize("producer_fails", [False, True])
def test_transfer_callers_check_both_processes_and_preserve_exclusions(
    tmp_path, monkeypatch, mode, producer_fails, capsys,
):
    source = tmp_path / "source"
    source.mkdir()
    (source / "present").write_text("source data")
    (source / ".env").write_text("LOCAL_SECRET=secret")
    (source / ".data").mkdir()
    (source / ".data/persistent").write_text("persistent state")
    (source / "caddy").mkdir()
    (source / "caddy/route").write_text("host ingress")
    destination = tmp_path / "destination"
    destination.mkdir()
    tar = shutil.which("tar")
    assert tar
    extract = [tar, "-xzf", "-", "-C", str(destination)]
    if mode == "resource-plane":
        extract.append("--strip-components=1")
    module = "sandbox.infra_deploy" if mode == "resource-plane" else "sandbox.app_deploy._deploy"
    monkeypatch.setattr(f"{module}.build_ssh_cmd", lambda _config, _cmd: extract)
    if producer_fails:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        wrapper = bin_dir / "tar"
        wrapper.write_text(
            f"#!/bin/sh\n{shlex.quote(tar)} \"$@\"\n"
            "echo 'simulated omitted archive member' >&2\nexit 2\n"
        )
        wrapper.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    config = VpsSshConfig(host="unused.invalid", key_path=tmp_path / "unused-key")
    if mode == "resource-plane":
        assert sync_resource_plane_to_vps(config, source_dir=source) is not producer_fails
        if producer_fails:
            assert "Source archive failed (exit 2)" in capsys.readouterr().err
        assert not (destination / ".data").exists()
        assert not (destination / "caddy").exists()
    elif producer_fails:
        with pytest.raises(RuntimeError, match="Source archive failed \\(exit 2\\)"):
            sync_local_app_to_vps(config, source, str(destination))
    else:
        sync_local_app_to_vps(config, source, str(destination))
    assert (destination / "present").read_text() == "source data"
    assert not (destination / ".env").exists()


def test_large_producer_stderr_does_not_block_streaming():
    stream_source_archive(
        [sys.executable, "-c", "import sys; sys.stderr.write('x' * 1000000); sys.stdout.buffer.write(b'payload')"],
        [sys.executable, "-c", "import sys; assert sys.stdin.buffer.read() == b'payload'"],
        timeout=5,
    )


@pytest.mark.parametrize("failure", ["timeout", "destination-startup"])
def test_failed_transfer_reaps_started_processes(monkeypatch, failure):
    real_popen = subprocess.Popen
    processes = []

    def start(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr("sandbox.source_transfer.subprocess.Popen", start)
    destination = [sys.executable, "-c", "import sys; sys.stdin.buffer.read()"]
    expected = RuntimeError
    if failure == "destination-startup":
        destination = ["/missing-transfer-destination"]
        expected = FileNotFoundError
    with pytest.raises(expected):
        stream_source_archive(
            [sys.executable, "-c", "import time; time.sleep(60)"], destination, timeout=0.2,
        )
    assert processes
    assert all(process.poll() is not None for process in processes)


def test_destination_failure_includes_its_error_and_stops_producer():
    with pytest.raises(RuntimeError, match="Destination extraction failed \\(exit 7\\): cannot extract"):
        stream_source_archive(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            [sys.executable, "-c", "import sys; sys.stderr.write('cannot extract'); sys.exit(7)"],
            timeout=5,
        )
