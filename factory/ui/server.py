"""Server runner for Factory Testing Console."""

import argparse
import os
import sys
import threading
import time
import webbrowser
import uvicorn

from factory.ui.app import create_app

DEFAULT_HOST = "127.0.0.1"


def get_default_port() -> int:
    """Returns the default port, respecting the PORT environment variable if valid."""
    env_port = os.getenv("PORT")
    if env_port is not None:
        try:
            return int(env_port)
        except ValueError:
            pass
    return 3010


DEFAULT_PORT = 3010


def start_server(
    host: str = DEFAULT_HOST,
    port: int | None = None,
    open_browser: bool = False,
    reload: bool = False,
) -> None:
    """Starts the Uvicorn server for the Factory Testing Console."""
    if port is None:
        port = get_default_port()
    app = create_app()

    if open_browser:
        def _open():
            time.sleep(1.0)
            url = f"http://{host}:{port}"
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open, daemon=True).start()

    from factory.ui.auth import get_auth_credentials
    creds = get_auth_credentials()

    print(f"\n========================================================")
    print(f"🏭 Factory Studio running at http://{host}:{port}")
    print(f"   Target Organization: software-factory-09-test")
    if creds.is_fallback:
        print(f"   ⚠️  SECURITY WARNING: Using local dev fallback ('{creds.username}':'{creds.password}')")
        print(f"      Set FACTORY_AUTH_USER and FACTORY_AUTH_PASS in production!")
    else:
        print(f"   🔒 HTTP Basic Auth enabled (user: '{creds.username}')")
    print(f"   Press Ctrl+C to terminate.")
    print(f"========================================================\n")

    uvicorn.run(app, host=host, port=port, log_level="info")


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for running the Factory Studio web interface."""
    parser = argparse.ArgumentParser(
        prog="factory.ui",
        description="Launch the Factory Studio web interface.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Bind host address (default: {DEFAULT_HOST})",
    )
    default_port = get_default_port()
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=default_port,
        help=f"Bind port number (default: {default_port})",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        default=False,
        help="Open web browser automatically on startup",
    )
    args = parser.parse_args(argv)

    start_server(host=args.host, port=args.port, open_browser=args.open)


if __name__ == "__main__":
    main()
