"""Server runner for Factory Testing Console."""

import argparse
import sys
import threading
import time
import webbrowser
import uvicorn

from factory.ui.app import create_app

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080


def start_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = False,
    reload: bool = False,
) -> None:
    """Starts the Uvicorn server for the Factory Testing Console."""
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

    print(f"\n========================================================")
    print(f"🏭 Factory Testing Console running at http://{host}:{port}")
    print(f"   Target Organization: software-factory-09-test")
    print(f"   Press Ctrl+C to terminate.")
    print(f"========================================================\n")

    uvicorn.run(app, host=host, port=port, log_level="info")


def main() -> None:
    """CLI entrypoint for running the Factory Testing Console."""
    parser = argparse.ArgumentParser(
        prog="factory.ui",
        description="Launch the Factory Testing Console web interface.",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Bind host address (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Bind port number (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        default=False,
        help="Open web browser automatically on startup",
    )
    args = parser.parse_args()

    start_server(host=args.host, port=args.port, open_browser=args.open)


if __name__ == "__main__":
    main()
