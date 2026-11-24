"""Modal Sandbox Management Tool.

Allows querying, inspecting, and terminating ephemeral Modal sandboxes by their
Modal Sandbox ID (sb-...) or their remote-control instance name (e.g. software-factory-286b1142)
across multiple Modal workspace profiles.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

# Ensure repository root is on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sandbox.lifecycle import (
    get_sandboxes,
    resolve_instance_name,
    terminate_sandbox,
    terminate_sandboxes,
)

__all__ = [
    "get_sandboxes",
    "resolve_instance_name",
    "terminate_sandbox",
    "terminate_sandboxes",
    "main",
]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List, inspect, and terminate Modal sandboxes by ID or instance name across profiles."
    )
    parser.add_argument("--profile", default=None, help="Modal workspace profile (default: all)")
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

    sandboxes = get_sandboxes(app_name=args.app, all_apps=args.all_apps, profile=args.profile)
    running_sandboxes = [s for s in sandboxes if s["running"]]

    targets = (args.terminate or []) + (args.keep or [])
    if targets and not args.all_apps and args.app == "software-factory":
        known = {s["id"] for s in running_sandboxes} | {s["name"] for s in running_sandboxes if s["name"]}
        if not any(t in known for t in targets):
            all_sandboxes = get_sandboxes(all_apps=True, profile=args.profile)
            all_running = [s for s in all_sandboxes if s["running"]]
            known_all = {s["id"] for s in all_running} | {s["name"] for s in all_running if s["name"]}
            if any(t in known_all for t in targets):
                sandboxes = all_sandboxes
                running_sandboxes = all_running

    if args.list or (not args.terminate and not args.keep):
        if args.json:
            print(json.dumps(sandboxes, indent=2))
        else:
            profile_label = f" [Profile: {args.profile}]" if args.profile else " [All Profiles]"
            print(f"Active Sandboxes{profile_label} ({len(running_sandboxes)} running / {len(sandboxes)} total):")
            for sb in sandboxes:
                status = "RUNNING" if sb["running"] else f"STOPPED (exit {sb['exit_code']})"
                name_str = f" [{sb['name']}]" if sb.get("name") else ""
                prof_str = f" ({sb['profile']})" if sb.get("profile") else ""
                print(f"  {sb['id']}{name_str}{prof_str}: {status}")
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
                prof_str = f" ({sb['profile']})" if sb.get("profile") else ""
                print(f"  {sb['id']} ({sb['name']}){prof_str}")
        return 0

    target_ids = [sb["id"] for sb in to_terminate]
    results = terminate_sandboxes(target_ids, dry_run=args.dry_run, profile=args.profile)

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
