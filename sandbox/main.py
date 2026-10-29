import argparse
import json
from pathlib import Path
import secrets
import sys
import time
import uuid

import modal

# Ensure repository root is on sys.path for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.image import (
    REMOTE_STARTUP_SCRIPT,
    SHARED_SECRET_NAME,
    browser_enabled,
    build_sandbox_image,
    get_gradle_volumes,
    load_ssh_pub_key,
)

from sandbox.config import (
    DEFAULT_ORG,
    TIMEOUT_SECS,
    IDLE_TIMEOUT_SECS,
    DEFAULT_WEB_PORT,
    DEFAULT_OPENCODE_PORT,
    DEFAULT_METRO_PORT,
    DEFAULT_T3_PORT,
)

from sandbox.cli import (
    SnapshotTTLAction,
    create_parser,
    validate_args,
    capture_snapshot,
    generate_ascii_qr,
    print_access_info,
)


def run_sandbox_launch(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser | None = None,
    repo_root: Path | None = None,
):
    if parser is None:
        parser = create_parser()

    if repo_root is None:
        repo_root = Path(__file__).resolve().parent.parent

    # Normalize repository name and detect testing mode
    clean_repo = args.repo.strip().rstrip("/") if args.repo else None
    is_testing = args.testing
    target_repo = None
    org_name = None
    bare_repo = None
    orgs_env_file = repo_root / "secrets" / "github-orgs.env"

    if clean_repo:
        if not orgs_env_file.is_file():
            parser.error(
                f"Organization credentials file not found: {orgs_env_file} (expected secrets/github-orgs.env)."
            )

        if "/" in clean_repo:
            org_name, raw_repo = clean_repo.split("/", 1)
        else:
            org_name = DEFAULT_ORG
            raw_repo = clean_repo

        if is_testing:
            org_name = DEFAULT_ORG
            if raw_repo.startswith("test-"):
                bare_repo = raw_repo
            else:
                bare_repo = f"test-{raw_repo}"
        else:
            bare_repo = raw_repo

        target_repo = f"{org_name}/{bare_repo}"

    if args.memory is not None:
        if not args.vm:
            parser.error("--memory can only be used with --vm.")
        if args.memory < 1:
            parser.error("--memory must be a positive integer number of GB.")
        print(
            "⚠️  Warning: --memory is deprecated. VM Sandboxes now use standard burstable RAM (128, 16384) MiB. "
            f"Using value to configure swapfile ({args.memory * 2} GB).",
            file=sys.stderr,
        )

    if args.opencode and args.opencode_port == DEFAULT_WEB_PORT:
        parser.error(
            f"--opencode-port cannot be {DEFAULT_WEB_PORT}: port {DEFAULT_WEB_PORT} is reserved for web servers and Cloudflare Tunnel."
        )

    if args.react_native:
        if args.metro_port == DEFAULT_WEB_PORT:
            parser.error(
                f"--metro-port cannot be {DEFAULT_WEB_PORT}: port {DEFAULT_WEB_PORT} is reserved for web servers and Cloudflare Tunnel."
            )
        if args.opencode and args.metro_port == args.opencode_port:
            parser.error(
                "--metro-port and --opencode-port must differ: a port can only be exposed once."
            )

    if args.t3 and args.t3_port == DEFAULT_WEB_PORT:
        parser.error(
            f"--t3-port cannot be {DEFAULT_WEB_PORT}: port {DEFAULT_WEB_PORT} is reserved for web servers and Cloudflare Tunnel."
        )

    if args.t3 and args.opencode and args.t3_port == args.opencode_port:
        parser.error(
            "--t3-port and --opencode-port must differ: a port can only be exposed once."
        )

    if args.t3 and args.react_native and args.t3_port == args.metro_port:
        parser.error(
            "--t3-port and --metro-port must differ: a port can only be exposed once."
        )

    pubkey_content = load_ssh_pub_key()

    random_id = uuid.uuid4().hex[:8]
    if args.name:
        app_name = args.name
        sandbox_name = f"{app_name}-{random_id}"
    else:
        app_name = bare_repo if bare_repo else "sandbox"
        sandbox_name = f"{app_name}-{random_id}"

    app = modal.App.lookup(app_name, create_if_missing=True)

    runtime_desc = "VM Sandbox" if args.vm else "Sandbox"

    browser_active = browser_enabled(
        browser=args.browser, opencode=args.opencode, agy=args.agy
    )

    if args.from_snapshot:
        image = modal.Image.from_id(args.from_snapshot)
    else:
        # Build the image incrementally based on the CLI flags passed.
        image = build_sandbox_image(
            opencode=args.opencode,
            agy=args.agy,
            browser=browser_active,
            modal_tooling=args.modal,
            react_native=args.react_native,
            t3=args.t3,
            herdr=args.herdr,
            pi=args.pi,
        )

    if clean_repo and orgs_env_file.is_file():
        image = image.add_local_file(orgs_env_file, "/root/secrets/github-orgs.env", copy=True)

    cloudflare_active = not args.no_cloudflare

    encrypted_ports: list[int] = []
    sandbox_secrets = [modal.Secret.from_name(SHARED_SECRET_NAME)]
    env: dict[str, str | None] = {
        "SSH_AUTHORIZED_KEY": pubkey_content,
        "PORT": str(DEFAULT_WEB_PORT),
        "HOSTNAME": "0.0.0.0",
        "APP_NAME": sandbox_name,
        "MODAL_APP_NAME": app_name,
        "SANDBOX_NAME": sandbox_name,
    }
    if args.from_snapshot:
        env["RESUME_SNAPSHOT"] = "1"
    if clean_repo is None:
        env["NO_REPO"] = "1"
    if target_repo:
        env["GH_REPO"] = target_repo
    if org_name:
        env["GH_ORG"] = org_name
    if args.full_clone:
        env["FULL_CLONE"] = "1"
    if not cloudflare_active:
        env["ENABLE_CLOUDFLARE"] = "0"

    memory_gb: int | None = None
    if args.vm:
        if args.memory is not None:
            memory_gb = args.memory
            swap_gb = memory_gb * 2
        else:
            swap_gb = 2
        env["SWAP_GB"] = str(swap_gb)
        env["ENABLE_DOCKER"] = "1"

    opencode_password = None
    if args.opencode:
        encrypted_ports.append(args.opencode_port)
        # Fresh password per launch, so nothing has to be pre-provisioned in the secret.
        opencode_password = secrets.token_urlsafe(16)
        sandbox_secrets.append(
            modal.Secret.from_dict({"OPENCODE_SERVER_PASSWORD": opencode_password})
        )
        # Explicit trigger for startup.sh; OPENCODE_PORT is only the port value.
        env["ENABLE_OPENCODE"] = "1"
        env["OPENCODE_PORT"] = str(args.opencode_port)

    t3_ssh_alias = getattr(args, "t3_ssh_host", None) or sandbox_name
    if args.t3:
        encrypted_ports.append(args.t3_port)
        env["ENABLE_T3"] = "1"
        env["T3_PORT"] = str(args.t3_port)
        env["FLAGS_enforce_kernel_ipv6_support"] = "false"
        env["T3_SSH_HOST"] = t3_ssh_alias

    if args.agy:
        # Explicit trigger for startup.sh to export the antigravity PATH in SSH sessions.
        env["ENABLE_ANTIGRAVITY"] = "1"

    if args.modal:
        env["ENABLE_MODAL"] = "1"

    if args.sops:
        env["ENABLE_SOPS"] = "1"

    if args.herdr:
        env["ENABLE_HERDR"] = "1"

    if args.pi:
        env["ENABLE_PI"] = "1"

    if browser_active:
        env["ENABLE_BROWSER"] = "1"

    volumes = {}
    if args.react_native:
        encrypted_ports.append(args.metro_port)
        env["ENABLE_REACT_NATIVE"] = "1"
        env["METRO_PORT"] = str(args.metro_port)
        volumes.update(get_gradle_volumes())\

    features = []
    if not args.no_cloudflare:
        features.append("Cloudflare Tunnel")
    if args.full_clone:
        features.append("Full Git Clone")
    if args.react_native:
        features.append("React Native")
    if args.agy:
        features.append("Antigravity")
    if args.opencode:
        features.append("OpenCode")
    if args.t3:
        features.append("T3 Code")
    if args.modal:
        features.append("Modal")
    if args.sops:
        features.append("SOPS")
    if args.herdr:
        features.append("Herdr")
    if args.pi:
        features.append("Pi")
    if browser_active:
        features.append("Browser")

    features_suffix = f" & {' & '.join(features)}" if features else ""
    from_suffix = f" from snapshot {args.from_snapshot}" if args.from_snapshot else ""
    print(
        f"🏝️  Launching Modal {runtime_desc}{from_suffix} with SSH"
        f"{features_suffix} (App: {app_name}, Sandbox: {sandbox_name})..."
    )

    sandbox_kwargs: dict = {
        "timeout": TIMEOUT_SECS,
        "idle_timeout": IDLE_TIMEOUT_SECS,
        "image": image,
        "app": app,
        "name": sandbox_name,
        "volumes": volumes,
        "unencrypted_ports": [22],
        "encrypted_ports": encrypted_ports,
        "cpu": (0.125, 4.0),
        "env": env,
    }
    sandbox_kwargs["runtime"] = "vm" if args.vm else "gvisor"
    sandbox_kwargs["memory"] = (128, 16384)

    try:
        with modal.enable_output():
            sandbox = modal.Sandbox.create(
                "bash",
                REMOTE_STARTUP_SCRIPT,
                args.github_branch,
                secrets=sandbox_secrets,
                **sandbox_kwargs,
            )
    except modal.exception.AlreadyExistsError as exc:
        print(
            f"❌ Sandbox '{sandbox_name}' already exists and is running in App '{app_name}': {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Retrieve forwarded tunnels
    ssh_info = None
    opencode_url = None
    metro_url = None
    t3_url = None
    try:
        tunnels = sandbox.tunnels()
        if 22 in tunnels:
            ssh_info = tunnels[22].tcp_socket
        if args.opencode and args.opencode_port in tunnels:
            opencode_url = tunnels[args.opencode_port].url
        if args.react_native and args.metro_port in tunnels:
            metro_url = tunnels[args.metro_port].url
        if args.t3 and args.t3_port in tunnels:
            t3_url = tunnels[args.t3_port].url
    except Exception as exc:
        print(f"⚠️  Could not obtain tunnel metadata: {exc}")

    t3_pair_url = None
    t3_qr_code = None
    if args.t3 and t3_url:
        clean_t3_url = t3_url.rstrip("/")
        # Configure T3 public URL and SSH host in the sandbox environment and server runtime state
        try:
            cfg_script = (
                f"import json, os, time\n"
                f"url = {json.dumps(clean_t3_url)}\n"
                f"ssh_host = {json.dumps(t3_ssh_alias)}\n"
                f"os.makedirs('/root/.t3', exist_ok=True)\n"
                f"with open('/root/.t3/public_url', 'w') as f:\n"
                f"    f.write(url + '\\n')\n"
                f"try:\n"
                f"    with open('/etc/machine-info', 'w') as f:\n"
                f"        f.write(f'PRETTY_HOSTNAME=\"{{ssh_host}}\"\\n')\n"
                f"except Exception:\n"
                f"    pass\n"
                f"for p in ['/etc/environment', '/root/.bashrc']:\n"
                f"    try:\n"
                f"        with open(p, 'a+') as f:\n"
                f"            f.seek(0)\n"
                f"            c = f.read()\n"
                f"            if 'T3_PUBLIC_URL=' not in c:\n"
                f"                f.write(f'export T3_PUBLIC_URL=\"{{url}}\"\\n')\n"
                f"            if 'T3_SSH_HOST=' not in c:\n"
                f"                f.write(f'export T3_SSH_HOST=\"{{ssh_host}}\"\\n')\n"
                f"    except Exception:\n"
                f"        pass\n"
                f"rt = '/root/.t3/userdata/server-runtime.json'\n"
                f"for _ in range(20):\n"
                f"    if os.path.isfile(rt):\n"
                f"        try:\n"
                f"            with open(rt, 'r') as f:\n"
                f"                d = json.load(f)\n"
                f"            if d.get('devUrl') != url:\n"
                f"                d['devUrl'] = url\n"
                f"                tmp = rt + '.tmp'\n"
                f"                with open(tmp, 'w') as f:\n"
                f"                    json.dump(d, f, indent=2)\n"
                f"                os.replace(tmp, rt)\n"
                f"            break\n"
                f"        except Exception:\n"
                f"            pass\n"
                f"    time.sleep(0.25)\n"
            )
            proc_cfg = sandbox.exec("python3", "-c", cfg_script)
            proc_cfg.wait()
        except Exception:
            pass

        # Mint the 24-hour pairing token directly from the container's pre-baked t3 binary
        try:
            proc = sandbox.exec("t3", "auth", "pairing", "create", "--ttl", "24h", "--json")
            if proc.wait() == 0:
                out = proc.stdout.read().strip()
                if out:
                    pairing_data = json.loads(out)
                    credential = pairing_data.get("credential")
                    if credential:
                        t3_pair_url = f"{clean_t3_url}/pair#token={credential}"
                        t3_qr_code = generate_ascii_qr(t3_pair_url)
        except Exception:
            pass

        # Fallback to /tmp/t3-pairing.json if direct exec failed
        if not t3_pair_url:
            for _ in range(6):
                try:
                    proc = sandbox.exec("cat", "/tmp/t3-pairing.json")
                    if proc.wait() == 0:
                        out = proc.stdout.read().strip()
                        if out:
                            pairing_data = json.loads(out)
                            credential = pairing_data.get("credential")
                            if credential:
                                t3_pair_url = f"{clean_t3_url}/pair#token={credential}"
                                t3_qr_code = generate_ascii_qr(t3_pair_url)
                                break
                except Exception:
                    pass
                time.sleep(0.5)

        if not t3_pair_url:
            t3_pair_url = clean_t3_url

    print_access_info(
        sandbox,
        app_name,
        sandbox_name=sandbox_name,
        ssh_info=ssh_info,
        opencode_url=opencode_url,
        opencode_port=args.opencode_port if args.opencode else None,
        opencode_password=opencode_password,
        metro_url=metro_url,
        metro_port=args.metro_port if args.react_native else None,
        t3_url=t3_url,
        t3_port=args.t3_port if args.t3 else None,
        t3_pair_url=t3_pair_url,
        t3_qr_code=t3_qr_code,
        t3_ssh_host=getattr(args, "t3_ssh_host", None),
        memory_gb=memory_gb,
        agy_enabled=args.agy,
        cloudflare_enabled=not args.no_cloudflare,
        sops_enabled=args.sops,
        is_vm=args.vm,
    )


def main():
    parser = create_parser()
    args = parser.parse_args()
    validate_args(parser, args)

    if args.snapshot:
        capture_snapshot(
            sandbox_id=args.snapshot,
            ttl_days=args.snapshot_ttl,
            terminate=args.terminate,
        )
        return

    run_sandbox_launch(args, parser=parser)


if __name__ == "__main__":
    main()
