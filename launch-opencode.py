# ---
# cmd: ["python", "13_sandboxes/opencode_server.py"]
# pytest: false
# ---

# # Run OpenCode in a Modal Sandbox

# This example demonstrates how to run [OpenCode](https://opencode.ai/docs)
# remotely and connect to it from your local terminal or browser.

# Combine self-hosted OpenCode with [serving a big, smart model](https://modal.com/docs/examples/very_large_models)
# on Modal and you've got "coding agents at home"!

# Coding agents are most useful when they have context and tools.
# Meta.

# ![A screenshot of the OpenCode Web UI showing this coding agent running its own code](https://modal-cdn.com/examples-opencode-server-webui.png)

# ## Set up OpenCode on Modal

import argparse
from pathlib import Path

import modal

MINUTES = 60
HOURS = 60 * MINUTES
OPENCODE_PORT = 4096

# First, we define a Modal container [Image](https://modal.com/docs/guide/images)
# with OpenCode installed.


def define_base_image() -> modal.Image:
    image = (
        modal.Image.from_registry("node:24-bookworm-slim")
        .apt_install("curl", "git", "gh")
        .run_commands(
            "corepack enable pnpm",
            "corepack prepare pnpm@10.31.0 --activate",
            "curl -fsSL https://opencode.ai/install | bash",
            "node -v",
            "pnpm -v",
        )
        .env({"PATH": "/root/.opencode/bin:${PATH}"})
    )

    # We also bring the global default OpenCode configuration along for the ride.

    CONFIG_PATH = Path("~/.config/opencode/opencode.json").expanduser()
    if CONFIG_PATH.exists():
        print("🏖️  Including config from", CONFIG_PATH)
        image = image.add_local_file(
            CONFIG_PATH, "/root/.config/opencode/opencode.json", copy=True
        )

    return image


# ## Clone a GitHub repository

# Next, we clone the code we want the agent to work on.
# The repository is cloned into the container image at build time,
# so it's available when the Sandbox starts.


def clone_github_repo(
    image: modal.Image, ref: str, secret: modal.Secret
) -> modal.Image:
    git_config = "git config --global advice.detachedHead false"
    clone_cmd = (
        f'REPO_NAME=$(basename "$GH_REPO") && '
        f'GIT_ASKPASS=echo git clone --quiet --depth 1 --branch {ref} --no-single-branch '
        f'https://oauth2:$GH_TOKEN@github.com/"$GH_REPO".git "/root/$REPO_NAME" && '
        f'if [ -n "$DOTENV_PRIVATE_KEY" ]; then echo "DOTENV_PRIVATE_KEY=$DOTENV_PRIVATE_KEY" > "/root/$REPO_NAME/.env.keys"; fi && '
        f'cd "/root/$REPO_NAME" && pnpm install'
    )

    print(f"🏖️  Cloning repository from secret at ref {ref}")
    return image.run_commands(
        git_config, clone_cmd, secrets=[secret], force_build=True
    )


# ## Start the Sandbox

# Now, we create a [Modal Sandbox](https://modal.com/docs/guide/sandboxes)
# to run our coding agent session.
# This Sandbox has our environment Image and a password for authentication.

# We open up the `OPENCODE_PORT` so that the server can be accessed over the Internet.


def create_sandbox(
    image: modal.Image,
    timeout: int,
    app: modal.App,
    secrets: list[modal.Secret],
) -> modal.Sandbox:
    print("🏖️  Creating sandbox")

    start_cmd = (
        f'if [ -n "$OPENCODE_GO_API_KEY" ]; then '
        f'mkdir -p ~/.local/share/opencode && '
        f'cat <<EOF > ~/.local/share/opencode/auth.json\n'
        f'{{\n'
        f'  "opencode-go": {{\n'
        f'    "type": "api",\n'
        f'    "key": "$OPENCODE_GO_API_KEY"\n'
        f'  }}\n'
        f'}}\n'
        f'EOF\n'
        f'fi && '
        f'REPO_NAME=$(basename "$GH_REPO") && '
        f'cd "/root/$REPO_NAME" && '
        f'exec opencode serve --hostname=0.0.0.0 --port={OPENCODE_PORT} --log-level=DEBUG --print-logs'
    )

    with modal.enable_output():
        return modal.Sandbox.create(
            "bash",
            "-c",
            start_cmd,
            encrypted_ports=[OPENCODE_PORT],
            secrets=secrets,
            timeout=timeout,
            image=image,
            app=app,
        )


# OpenCode is truly open -- there are many interfaces to the underlying
# coding agent server.
# Here we print information for:
# - directly accessing the underlying Modal Sandbox for debugging or "pair coding" with the agent
# - accessing the Web UI from a local browser (with authentication!)
# - accessing the TUI from your local terminal


def print_access_info(sandbox: modal.Sandbox, secret_collection: str):
    print(
        "🏖️  Access the sandbox directly:",
        f"modal shell {sandbox.object_id}",
        sep="\n\t",
    )

    tunnel = sandbox.tunnels()[OPENCODE_PORT]
    print(
        "🏖️  Access the WebUI:",
        tunnel.url,
        "Username: opencode",
        sep="\n\t",
    )
    print(
        "🏖️  Access the TUI:",
        f"OPENCODE_SERVER_PASSWORD=YOUR_PASSWORD opencode attach {tunnel.url}",
        sep="\n\t",
    )
    print(
        "🏖️  Display the password:",
        f"modal shell --secret {secret_collection} --cmd 'env | grep OPENCODE_SERVER_PASSWORD='",
        sep="\n\t",
    )


# The server is secured via secrets in a [Modal Secret](https://modal.com/docs/guide/secrets).
# You can create one by heading to the [Secrets Dashboard](https://modal.com/secrets)
# and creating a new "Custom" Secret. The secret collection should define:
# - `OPENCODE_SERVER_PASSWORD`: password for server authentication
# - `GH_TOKEN`: GitHub personal access token for git authentication
# - `GH_REPO`: GitHub repository in owner/repo format (e.g. anveshak71/db-manage)
# - `DOTENV_PRIVATE_KEY`: private key for dotenv decryption (creates .env.keys)
# - `OPENCODE_GO_API_KEY`: API key for OpenCode Go (creates ~/.local/share/opencode/auth.json)

# The CLI will also give you a helpful one-liner you can use to recover the password
# with your Modal credentials in case you forget it.


# ## Putting it all together


def main(
    timeout: int,
    app_name: str,
    github_ref: str,
    secret_collection: str,
):
    app = modal.App.lookup(app_name, create_if_missing=True)
    image = define_base_image()

    secret = modal.Secret.from_name(secret_collection)
    image = clone_github_repo(image, github_ref, secret)

    sandbox_secrets = [secret]

    sandbox = create_sandbox(image, timeout, app, sandbox_secrets)
    print_access_info(sandbox, secret_collection)


# ## Command-line options

# This script supports configuration via command-line arguments.
# Run with `--help` to see all options.


def parse_timeout(timeout_str: str) -> int:
    if timeout_str.endswith("h"):
        minutes = int(timeout_str[:-1]) * 60
    elif timeout_str.endswith("m"):
        minutes = int(timeout_str[:-1])
    else:
        minutes = int(timeout_str) * 60

    if minutes < 1:
        raise argparse.ArgumentTypeError("Timeout must be at least 1 minute")
    if minutes > 24 * 60:
        raise argparse.ArgumentTypeError("Timeout cannot exceed 24 hours")

    return minutes * MINUTES


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Launch OpenCode server on Modal")
    parser.add_argument(
        "--timeout",
        type=str,
        default="12",
        help="Server timeout (e.g. 2h, 90m). No suffix -> hours. Default: 12",
    )
    parser.add_argument(
        "--app-name",
        type=str,
        default="nodejs-opencode-server",
        help="Modal app name. Default: nodejs-opencode-server",
    )
    parser.add_argument(
        "--github-ref",
        type=str,
        default="main",
        help="Git ref to checkout (branch, tag, SHA). Default: main",
    )
    parser.add_argument(
        "--secret-collection",
        "--secret",
        dest="secret_collection",
        type=str,
        required=True,
        help="Modal secret collection name containing credentials and configuration.",
    )

    args = parser.parse_args()

    main(
        parse_timeout(args.timeout),
        args.app_name,
        args.github_ref,
        args.secret_collection,
    )
