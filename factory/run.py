#!/usr/bin/env python3
"""CLI Dispatcher and Host Runner for Software Factory Jobs.

Local command-line interface used by developers to launch autonomous software
factory jobs against target projects. Validates project secrets locally, provisions
ephemeral Modal Sandboxes (Standard or VM), streams live logs to the terminal via
modal.enable_output(), and propagates sandbox exit codes cleanly.
"""

import argparse
from pathlib import Path
import sys
from typing import Sequence, TextIO

# Ensure software-factory repository root is on sys.path for direct script execution
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import modal

from factory.orchestrator import (
    FACTORY_TIMEOUT_SECS,
    dispatch_job,
    resolve_secrets_dir,
)

DEFAULT_MODEL: str = "deepseek-v4.1-flash"
SUPPORTED_MODELS: tuple[str, ...] = ("deepseek-v4.1-flash", "mimo-v2.6-flash")

MODEL_MAP: dict[str, str] = {
    "deepseek": "deepseek-v4.1-flash",
    "deepseek-flash": "deepseek-v4.1-flash",
    "deepseek-v4.1-flash": "deepseek-v4.1-flash",
    "deepseek v4.1 flash": "deepseek-v4.1-flash",
    "mimo": "mimo-v2.6-flash",
    "mimo-flash": "mimo-v2.6-flash",
    "mimo-v2.6-flash": "mimo-v2.6-flash",
    "mimo v2.6 flash": "mimo-v2.6-flash",
}


def normalize_model_name(model: str | None) -> str:
    """Normalizes model names and aliases to canonical model identifiers.

    Supports toggling between DeepSeek V4.1 Flash (default) and MiMo-V2.6-Flash.
    """
    if not model:
        return DEFAULT_MODEL

    cleaned = model.strip().lower()
    if cleaned in MODEL_MAP:
        return MODEL_MAP[cleaned]

    raise ValueError(
        f"Unsupported model: '{model}'. Supported models are: "
        f"DeepSeek V4.1 Flash ('{DEFAULT_MODEL}') or MiMo-V2.6-Flash ('{SUPPORTED_MODELS[1]}')"
    )


def create_parser() -> argparse.ArgumentParser:
    """Constructs the argument parser for the CLI Dispatcher."""
    parser = argparse.ArgumentParser(
        prog="factory/run.py",
        description="Launch an autonomous software factory assembly line against a target project.",
    )

    parser.add_argument(
        "-p",
        "--project",
        required=True,
        help="Target project name (under secrets/<project> or software-factory-09-test/<project> when testing).",
    )
    parser.add_argument(
        "-f",
        "--feature",
        required=True,
        help="Feature slug matching target repository .scratch/<feature>/ (e.g. 'queues-page').",
    )
    parser.add_argument(
        "-i",
        "--issue",
        default=None,
        help="Optional specific ticket ID (e.g. '01'). Defaults to full autonomous batch across unblocked frontier tickets.",
    )
    parser.add_argument(
        "--vm",
        action="store_true",
        default=False,
        help="Dynamically launch a full VM Sandbox with Docker daemon support instead of Standard Sandbox.",
    )
    parser.add_argument(
        "--memory",
        dest="memory_gb",
        type=int,
        default=None,
        help="Memory allocation in GB (for VM sandboxes).",
    )
    parser.add_argument(
        "-m",
        "--model",
        default=DEFAULT_MODEL,
        help="Toggle LLM between 'DeepSeek V4.1 Flash' (default) and 'MiMo-V2.6-Flash'.",
    )
    parser.add_argument(
        "--testing",
        "--test",
        dest="testing",
        action="store_true",
        default=False,
        help="Target isolated test repositories under canonical test organization software-factory-09-test/.",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parses and validates command line arguments."""
    parser = create_parser()
    args = parser.parse_args(argv)
    try:
        args.model = normalize_model_name(args.model)
    except ValueError as e:
        parser.error(str(e))
    return args


def validate_project_secrets(
    project: str,
    testing: bool = False,
    repo_root: Path | None = None,
) -> Path:
    """Validates locally that the target project or organization secret directory exists.

    Args:
        project: Target project name (e.g. 'repo-horizon', 'test3', or 'software-factory-09-test/test3').
        testing: Whether to resolve from canonical Test Organization under 'secrets_org/' per ADR 0031.
        repo_root: Optional software factory repository root.

    Returns:
        Path to the project or organization secrets directory.

    Raises:
        FileNotFoundError: If the directory, fetch.env, or token is missing.
    """
    return resolve_secrets_dir(project=project, testing=testing, repo_root=repo_root)


def main(
    argv: Sequence[str] | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    repo_root: Path | None = None,
) -> int:
    """Main CLI entry point for the Software Factory CLI Dispatcher.

    Validates project secrets locally, provisions the Modal sandbox via
    the factory spawner, streams live execution logs to stdout/stderr via
    modal.enable_output(), and propagates the sandbox exit code cleanly.
    """
    args = parse_args(argv)

    # Validate locally that target project fetch.env exists before cloud launch
    try:
        validate_project_secrets(
            project=args.project,
            testing=args.testing,
            repo_root=repo_root,
        )
    except FileNotFoundError as err:
        stderr.write(f"Error: {err}\n")
        stderr.flush()
        return 1

    # Trigger Modal spawner and stream live execution logs
    with modal.enable_output():
        return dispatch_job(
            project=args.project,
            feature=args.feature,
            issue=args.issue,
            vm=args.vm,
            testing=args.testing,
            model=args.model,
            memory_gb=args.memory_gb,
            stdout=stdout,
            stderr=stderr,
        )


if __name__ == "__main__":
    sys.exit(main())

