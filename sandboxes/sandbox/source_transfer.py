"""Stream a source archive and account for both processes before deployment."""

from __future__ import annotations

import os
import signal
import subprocess
import tempfile
import time
from typing import BinaryIO, Sequence


def _stop_process(process: subprocess.Popen[bytes]) -> None:
    """Reap an unfinished process and the children in its private process group."""
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    finally:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _error_detail(label: str, process: subprocess.Popen[bytes], errors: BinaryIO) -> str:
    if process.returncode == 0:
        return ""
    errors.seek(0)
    message = errors.read(8192).decode("utf-8", errors="replace").strip()
    return f"{label} failed (exit {process.returncode}): {message}"


def stream_source_archive(
    archive_command: Sequence[str],
    destination_command: Sequence[str],
    *,
    timeout: int = 180,
) -> None:
    """Require archive production and remote extraction to finish successfully.

    Stderr goes to temporary files so either process can write freely while the
    archive streams. One deadline covers archive production and extraction.
    """
    producer = None
    consumer = None
    deadline = time.monotonic() + timeout
    with tempfile.TemporaryFile() as producer_errors, tempfile.TemporaryFile() as consumer_errors:
        try:
            producer = subprocess.Popen(
                archive_command, stdout=subprocess.PIPE, stderr=producer_errors,
                start_new_session=os.name == "posix",
            )
            try:
                consumer = subprocess.Popen(
                    destination_command, stdin=producer.stdout, stdout=subprocess.DEVNULL,
                    stderr=consumer_errors, start_new_session=os.name == "posix",
                )
            finally:
                if producer.stdout:
                    producer.stdout.close()
            consumer.wait(timeout=max(0, deadline - time.monotonic()))
            if consumer.returncode:
                _stop_process(producer)
            producer.wait(timeout=max(0, deadline - time.monotonic()))
            errors = [
                _error_detail("Source archive", producer, producer_errors),
                _error_detail("Destination extraction", consumer, consumer_errors),
            ]
            failures = [error for error in errors if error]
            if failures:
                raise RuntimeError("\n".join(failures))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Source transfer timed out after {timeout} seconds.") from exc
        finally:
            if consumer is not None:
                _stop_process(consumer)
            if producer is not None:
                _stop_process(producer)
