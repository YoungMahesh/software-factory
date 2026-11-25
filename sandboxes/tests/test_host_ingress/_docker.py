"""Local Docker stand-in that observes files staged by the real SSH scripts."""

import json
import os
from pathlib import Path
import sys

root = Path(os.environ["INGRESS_TEST_ROOT"])
state_path = Path(os.environ["INGRESS_TEST_STATE"])
state = json.loads(state_path.read_text())
args = sys.argv[1:]
state.setdefault("commands", []).append(args)


def finish(code=0, output=""):
    state_path.write_text(json.dumps(state))
    if output:
        print(output, file=sys.stderr if code else sys.stdout)
    sys.exit(code)


def conf_files():
    return {
        path.relative_to(root).as_posix(): path.read_text()
        for path in (root / "conf").rglob("*") if path.is_file()
    }

if args[0] == "info":
    finish(1 if state.get("daemon_unavailable") else 0)

if args[0] == "inspect":
    app = state.get("apps", {}).get(args[-1])
    if app is not None:
        if ".Config.Labels" in " ".join(args):
            finish(output=json.dumps(app["labels"]))
        finish(output="healthy" if app["running"] else "exited")
    if ".State.Running" in " ".join(args):
        finish(output=str(state["running"]).lower())
    if ".NetworkSettings.Networks" in " ".join(args):
        finish(output=json.dumps({name: {} for name in state.get("networks", [])}))
    if ".Image" in " ".join(args):
        finish(output="sha256:previous-image")
    if ".Id" in " ".join(args):
        finish(output=f"container-{state.get('generation', 0)} start-time")
if args[0] == "ps":
    if "-a" in args:
        finish(output="\n".join(["caddy", *state.get("apps", {})]))
    finish(output="other-proxy 0.0.0.0:80->80/tcp" if state.get("ports_busy") else "")
if args[0] == "network":
    if args[1] == "ls":
        finish(output="\n".join(state.get("networks", [])))
    if args[1] == "inspect":
        finish(0 if args[2] in state.get("networks", []) else 1)
    if args[1] in ("create", "connect"):
        state.setdefault("networks", []).append(args[2])
        finish()
if args[0] == "exec":
    if not state["running"]:
        finish(1, "container is stopped")
    if "list-modules" in args:
        finish(output="dns.providers.cloudflare" if state.get("cloudflare") else "")
    if "validate" in args:
        if any("INVALID" in text for text in conf_files().values()):
            finish(1, "invalid configuration")
        finish()
    if "reload" in args:
        state["reloads"] = state.get("reloads", 0) + 1
        if state.get("fail_reloads", 0):
            state["fail_reloads"] -= 1
            finish(1, "simulated reload failure")
        state["active"] = conf_files()
        finish()
if args[0] == "compose" and "-p" in args:
    project = args[args.index("-p") + 1]
    container_name = f"{project}-web"
    if "down" in args:
        if state.get("fail_app_stops", 0):
            state["fail_app_stops"] -= 1
            finish(1, "simulated app stop failure")
        state.setdefault("apps", {}).pop(container_name, None)
        finish()
    if "build" in args:
        if state.get("fail_app_builds", 0):
            state["fail_app_builds"] -= 1
            finish(1, "simulated app build failure")
        finish()
    if "run" in args:
        state["migrations"] = state.get("migrations", 0) + 1
        finish()
    if "up" in args:
        state.setdefault("apps", {})[container_name] = {
            "labels": {
                "com.docker.compose.project": project,
                "com.docker.compose.project.working_dir": os.getcwd(),
            },
            "running": True,
        }
        finish()
if args[0] == "compose" and "up" in args:
    state["starts"] = state.get("starts", 0) + 1
    if state.get("fail_starts", 0):
        state["fail_starts"] -= 1
        state["running"] = False
        finish(1, "simulated startup failure")
    if "--build" in args:
        if not (root / "Dockerfile").is_file():
            finish(1, "Dockerfile missing from the Compose build context")
        state["cloudflare"] = True
    state["running"] = True
    state["generation"] = state.get("generation", 0) + 1
    state["active"] = conf_files()
    finish()
if args[0] == "stop":
    state["running"] = False
    finish()
finish(1, f"Unsupported Docker call in test: {args}")
