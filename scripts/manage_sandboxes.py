"""Modal Sandbox Management Tool.

Allows querying, inspecting, and terminating ephemeral Modal sandboxes by their
Modal Sandbox ID (sb-...) or their remote-control instance name (e.g. software-factory-286b1142).
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

import modal


def resolve_instance_name(sb: modal.Sandbox) -> str | None:
    """Attempts to resolve the instance name configured inside the sandbox container."""
    tags = sb.get_tags() if hasattr(sb, "get_tags") else {}
    if "instance_name" in tags:
        return tags["instance_name"]
    if "name" in tags:
        return tags["name"]

    try:
        proc = sb.exec("cat", "/tmp/agy-remote-control.log")
        out = proc.stdout.read()
        for line in out.splitlines():
            if "Instance name set to" in line and '"' in line:
                return line.split('"')[1]
    except Exception:
        pass

    try:
        proc = sb.exec("cat", "/root/.gemini/config/config.json")
        data = json.loads(proc.stdout.read())
        cfg_name = data.get("userSettings", {}).get("cliRemoteControlHostname")
        if cfg_name:
            return cfg_name
    except Exception:
        pass

    return None


def get_sandboxes(app_name: str | None = "software-factory", all_apps: bool = False) -> list[dict[str, Any]]:
    """Fetches and inspects active Modal sandboxes."""
    app_id = None
    if app_name and not all_apps:
        try:
            app = modal.App.lookup(app_name)
            app_id = app.app_id
        except Exception:
            app_id = None

    sb_generator = modal.Sandbox.list(app_id=app_id) if app_id else modal.Sandbox.list()

    sandboxes = []
    for sb in sb_generator:
        poll_code = sb.poll()
        is_running = poll_code is None
        name = resolve_instance_name(sb) if is_running else None
        sandboxes.append({
            "id": sb.object_id,
            "name": name,
            "running": is_running,
            "exit_code": poll_code,
        })
    return sandboxes


def terminate_sandboxes(
    target_ids: list[str],
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Terminates sandboxes by their object ID."""
    results = []
    for sb_id in target_ids:
        if dry_run:
            results.append({"id": sb_id, "status": "dry-run", "exit_code": None})
            continue

        try:
            sb = modal.Sandbox.from_id(sb_id)
            sb.terminate(wait=True)
            results.append({"id": sb_id, "status": "terminated", "exit_code": sb.poll()})
        except Exception as e:
            results.append({"id": sb_id, "status": "error", "error": str(e)})
    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List, inspect, and terminate Modal sandboxes by ID or instance name."
    )
    parser.add_argument("--app", default="software-factory", help="Modal App name (default: software-factory)")
    parser.add_argument("--all-apps", action="store_true", help="Scan environment-wide without scoping to an App")
    parser.add_argument("--list", action="store_true", help="List all active sandboxes")
    parser.add_argument("--terminate", nargs="+", help="Sandbox IDs or instance names to terminate")
    parser.add_argument(
        "--keep",
        nargs="+",
        help="Sandbox IDs or instance names to preserve (all other running sandboxes are terminated)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the action without actually terminating any sandboxes",
    )
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")

    args = parser.parse_args()

    sandboxes = get_sandboxes(app_name=args.app, all_apps=args.all_apps)
    running_sandboxes = [s for s in sandboxes if s["running"]]

    if args.list or (not args.terminate and not args.keep):
        if args.json:
            print(json.dumps(sandboxes, indent=2))
        else:
            print(f"Active Sandboxes ({len(running_sandboxes)} running / {len(sandboxes)} total):")
            for sb in sandboxes:
                status = "RUNNING" if sb["running"] else f"STOPPED (exit {sb['exit_code']})"
                name_str = f" [{sb['name']}]" if sb["name"] else ""
                print(f"  {sb['id']}{name_str}: {status}")
        return 0

    to_terminate: list[dict[str, Any]] = []
    to_keep: list[dict[str, Any]] = []

    if args.keep:
        keep_set = set(args.keep)
        for sb in running_sandboxes:
            if sb["id"] in keep_set or (sb["name"] and sb["name"] in keep_set):
                to_keep.append(sb)
            else:
                to_terminate.append(sb)
    elif args.terminate:
        term_set = set(args.terminate)
        for sb in running_sandboxes:
            if sb["id"] in term_set or (sb["name"] and sb["name"] in term_set):
                to_terminate.append(sb)
            else:
                to_keep.append(sb)

    if not to_terminate:
        if args.json:
            print(json.dumps({"action": "none", "message": "No matching sandboxes to terminate.", "running": running_sandboxes}, indent=2))
        else:
            print("No matching sandboxes to terminate.")
            print("Running sandboxes:")
            for sb in running_sandboxes:
                print(f"  {sb['id']} ({sb['name']})")
        return 0

    target_ids = [sb["id"] for sb in to_terminate]
    results = terminate_sandboxes(target_ids, dry_run=args.dry_run)

    if args.json:
        print(json.dumps({
            "action": "terminate",
            "dry_run": args.dry_run,
            "terminated": results,
            "kept": to_keep,
        }, indent=2))
    else:
        prefix = "[DRY-RUN] Would terminate" if args.dry_run else "Terminated"
        print(f"{prefix} {len(results)} sandbox(es):")
        for res in results:
            matching_sb = next((s for s in to_terminate if s["id"] == res["id"]), None)
            name_label = f" ({matching_sb['name']})" if matching_sb and matching_sb["name"] else ""
            status_label = f" -> {res['status']}" if not args.dry_run else ""
            print(f"  {res['id']}{name_label}{status_label}")

        print(f"\nKept {len(to_keep)} active sandbox(es):")
        for sb in to_keep:
            name_label = f" ({sb['name']})" if sb["name"] else ""
            print(f"  {sb['id']}{name_label}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
