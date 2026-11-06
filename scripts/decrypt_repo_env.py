#!/usr/bin/env python3
"""Decrypt and restore repository environment secrets locally from .secrets/env.map.

Restores SOPS-encrypted environment files under .secrets/ to their workspace
destination paths as defined in ADR 0077, without launching a Modal sandbox.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys


DEFAULT_KEY_FILE = Path.home() / ".config" / "sops" / "age" / "keys.txt"


@dataclass
class DecryptResult:
    src_rel: str
    dest_rel: str
    dest_path: Path
    content: str
    written: bool


def parse_env_map(env_map_path: Path) -> list[tuple[str, str]]:
    """Parses .secrets/env.map returning a list of (src_rel, dest_rel) tuples."""
    if not env_map_path.is_file():
        raise FileNotFoundError(f"Environment manifest not found: {env_map_path}")

    mappings: list[tuple[str, str]] = []
    for line in env_map_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            k, v = stripped.split("=", 1)
            src = k.strip()
            dest = v.strip().lstrip("/")
            if src and dest:
                mappings.append((src, dest))
    return mappings


def run_sops_decrypt(encrypted_file: Path, key_file: Path | None = None) -> str:
    """Decrypts a SOPS-encrypted file returning its plaintext string."""
    if not shutil.which("sops"):
        raise RuntimeError("sops executable not found in PATH.")

    if not encrypted_file.is_file():
        raise FileNotFoundError(f"Encrypted secret file not found: {encrypted_file}")

    env = os.environ.copy()
    target_key_file = key_file or DEFAULT_KEY_FILE
    if target_key_file.is_file() and "SOPS_AGE_KEY_FILE" not in env:
        env["SOPS_AGE_KEY_FILE"] = str(target_key_file)

    cmd = ["sops", "decrypt", str(encrypted_file)]
    res = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if res.returncode != 0:
        raise RuntimeError(f"SOPS decryption failed for {encrypted_file}: {res.stderr.strip()}")

    return res.stdout


def decrypt_repo_env(
    repo_path: Path,
    mapping_filter: str | None = None,
    to_stdout: bool = False,
    force: bool = False,
    dry_run: bool = False,
    key_file: Path | None = None,
) -> list[DecryptResult]:
    """Decrypts repository environment files defined in .secrets/env.map."""
    repo_path = repo_path.resolve()
    secrets_dir = repo_path / ".secrets"
    env_map_path = secrets_dir / "env.map"

    mappings = parse_env_map(env_map_path)
    if mapping_filter:
        mappings = [m for m in mappings if m[0] == mapping_filter or m[1] == mapping_filter]
        if not mappings:
            raise ValueError(f"No mapping matching '{mapping_filter}' found in {env_map_path}")

    results: list[DecryptResult] = []

    for src_rel, dest_rel in mappings:
        src_file = secrets_dir / src_rel
        dest_file = repo_path / dest_rel

        if not src_file.is_file():
            raise FileNotFoundError(f"Mapped encrypted file not found: {src_file}")

        if dest_file.exists() and not force and not to_stdout and not dry_run:
            raise FileExistsError(
                f"Destination file {dest_file} already exists. Pass --force to overwrite."
            )

        if dry_run:
            results.append(
                DecryptResult(
                    src_rel=src_rel,
                    dest_rel=dest_rel,
                    dest_path=dest_file,
                    content="",
                    written=False,
                )
            )
            continue

        plaintext = run_sops_decrypt(src_file, key_file=key_file)

        written = False
        if not to_stdout:
            dest_file.parent.mkdir(parents=True, exist_ok=True)
            dest_file.write_text(plaintext, encoding="utf-8")
            os.chmod(dest_file, 0o600)
            written = True

        results.append(
            DecryptResult(
                src_rel=src_rel,
                dest_rel=dest_rel,
                dest_path=dest_file,
                content=plaintext,
                written=written,
            )
        )

    return results


def parse_args(argv: list[str] | None = None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Decrypt repository .env files using SOPS and .secrets/env.map without launching a sandbox.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=".",
        help="Path to the repository root directory.",
    )
    parser.add_argument(
        "-m",
        "--mapping",
        default=None,
        help="Decrypt only a specific mapping entry (by source secret or dest path).",
    )
    parser.add_argument(
        "-s",
        "--stdout",
        action="store_true",
        help="Print decrypted contents to stdout instead of writing to disk.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing destination .env files on disk.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without modifying disk.",
    )
    parser.add_argument(
        "-k",
        "--key-file",
        default=None,
        type=Path,
        help="Explicit path to Age private key file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_path = Path(args.repo_path)

    try:
        results = decrypt_repo_env(
            repo_path=repo_path,
            mapping_filter=args.mapping,
            to_stdout=args.stdout,
            force=args.force,
            dry_run=args.dry_run,
            key_file=args.key_file,
        )

        if args.dry_run:
            print("🔍 [DRY RUN] Would decrypt:")
            for res in results:
                print(f"   • {res.src_rel} -> {res.dest_rel} ({res.dest_path})")
            return 0

        if args.stdout:
            for i, res in enumerate(results):
                if len(results) > 1:
                    print(f"--- {res.dest_rel} ({res.src_rel}) ---")
                print(res.content.rstrip())
            return 0

        print(f"🔓 Decrypted {len(results)} file(s) for {repo_path}:")
        for res in results:
            print(f"   • .secrets/{res.src_rel} -> {res.dest_rel} (mode 0600)")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
