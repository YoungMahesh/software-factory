"""In-Sandbox Interactive Terminal WebSocket route.

Connects browser xterm.js terminals directly to Modal container pseudo-terminals
(sandbox.exec(pty=True)) with full-duplex streaming and automatic process termination.
"""

import asyncio
import logging
import threading
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from factory.ui.github import strip_repo_owner
from factory.ui.registry import PreviewRegistry, preview_registry

logger = logging.getLogger("factory.ui.routes.terminal")

router = APIRouter()


def _resolve_active_sandbox(ws: WebSocket, clean_repo: str, bare_repo: str) -> tuple[Any, str | None]:
    preview_reg: PreviewRegistry = getattr(getattr(ws.app, "state", None), "preview_reg", preview_registry)
    for r in (bare_repo, clean_repo):
        sandbox, url = preview_reg.get_active_sandbox(r)
        if sandbox is not None:
            return sandbox, url
    return None, None


@router.websocket("/api/repos/{repo:path}/terminal/ws")
@router.websocket("/api/repos/{repo}/terminal/ws")
async def terminal_websocket(websocket: WebSocket, repo: str) -> None:
    """Full-duplex WebSocket bridge to an interactive login bash subshell in Modal Sandbox."""
    await websocket.accept()

    clean_repo = strip_repo_owner(repo)
    bare_repo = clean_repo.split("/")[-1]

    active_sandbox, _ = _resolve_active_sandbox(websocket, clean_repo, bare_repo)
    if active_sandbox is None:
        msg = (
            f"\r\n\x1b[33m[Studio Terminal] Sandbox container is not running for repository '{clean_repo}'.\x1b[0m\r\n"
            "\x1b[90mPlease start a Live Preview or dispatch a pipeline job to provision the container.\x1b[0m\r\n"
        )
        try:
            await websocket.send_text(msg)
            await websocket.close(code=1000)
        except Exception:
            pass
        return

    try:
        proc = active_sandbox.exec(
            "bash",
            "--login",
            workdir=f"/root/{bare_repo}",
            pty=True,
        )
    except Exception as e:
        logger.warning("Failed to exec interactive bash in sandbox: %s", e)
        err_msg = f"\r\n\x1b[31m[Studio Terminal] Failed to launch interactive shell: {e}\x1b[0m\r\n"
        try:
            await websocket.send_text(err_msg)
            await websocket.close(code=1011)
        except Exception:
            pass
        return

    loop = asyncio.get_running_loop()
    stop_event = threading.Event()

    def read_stdout() -> None:
        try:
            for chunk in proc.stdout:
                if stop_event.is_set() or chunk is None:
                    break
                text = chunk.decode("utf-8", errors="replace") if isinstance(chunk, bytes) else str(chunk)
                if text:
                    fut = asyncio.run_coroutine_threadsafe(websocket.send_text(text), loop)
                    try:
                        fut.result(timeout=5.0)
                    except Exception:
                        break
        except Exception as e:
            logger.debug("Terminal stdout reader stopped: %s", e)
        finally:
            if not stop_event.is_set():
                try:
                    asyncio.run_coroutine_threadsafe(
                        websocket.send_text("\r\n\x1b[90m[Process completed]\x1b[0m\r\n"),
                        loop,
                    )
                except Exception:
                    pass

    reader_thread = threading.Thread(target=read_stdout, daemon=True, name=f"term-stdout-{bare_repo}")
    reader_thread.start()

    try:
        while not stop_event.is_set():
            data = await websocket.receive_text()
            # Ignore client-side terminal resize event frames if passed as JSON
            if data.startswith("{") and '"resize"' in data:
                continue

            if hasattr(proc, "stdin") and proc.stdin is not None:
                if hasattr(proc.stdin, "write"):
                    proc.stdin.write(data)
                if hasattr(proc.stdin, "drain"):
                    res = proc.stdin.drain()
                    if asyncio.iscoroutine(res):
                        await res
                elif hasattr(proc.stdin, "flush"):
                    proc.stdin.flush()
    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.info("Terminal WebSocket disconnected for repo '%s'", bare_repo)
    except Exception as e:
        logger.warning("Error in terminal WebSocket relay: %s", e)
    finally:
        stop_event.set()
        # Immediately terminate the backend container process handle to prevent leaked processes.
        # First send SIGINT (\x03) and exit to bash, close stdin with write_eof(), and flush via drain().
        if hasattr(proc, "stdin") and proc.stdin is not None:
            if hasattr(proc.stdin, "write"):
                try:
                    proc.stdin.write("\x03exit\r\n")
                except Exception:
                    pass
            if hasattr(proc.stdin, "write_eof"):
                try:
                    proc.stdin.write_eof()
                except Exception:
                    pass
            if hasattr(proc.stdin, "drain"):
                try:
                    res = proc.stdin.drain()
                    if asyncio.iscoroutine(res):
                        await res
                except Exception:
                    pass

        # Also call terminate() or kill() if implemented on the process handle
        if hasattr(proc, "terminate"):
            try:
                proc.terminate()
            except Exception:
                pass
        elif hasattr(proc, "kill"):
            try:
                proc.kill()
            except Exception:
                pass

        reader_thread.join(timeout=0.5)
