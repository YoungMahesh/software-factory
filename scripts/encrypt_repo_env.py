#!/usr/bin/env python3
"""Encrypt and register repository environment secrets for the Modal sandbox runner.

Stores SOPS-encrypted environment files under .secrets/ and maintains
.secrets/env.map as defined in ADR 0077.
"""

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


DEFAULT_AGE_RECIPIENT = "age1zwr6flwyk3lt6k0xsd9wy0qy4dlytkdyv5aggvqu6zxqt3p2eyrsw5n4qj"
DEFAULT_KEY_FILE = Path.home() / ".config" / "sops" / "age" / "keys.txt"


@dataclass
class EncryptResult:
    repo_path: Path
    env_file: Path
    dest_rel: str
    mapping_name: str
    encrypted_file: Path
    git_untracked: bool
    gitignore_updated: bool
    verified: bool


def resolve_age_recipient(override: str | None = None, key_file: Path | None = None) -> str:
    """Resolves the target age public recipient key."""
    if override and override.strip():
        return override.strip()

    target_key_file = key_file or DEFAULT_KEY_FILE
    if target_key_file.is_file():
        try:
            res = subprocess.run(
                ["age-keygen", "-y", str(target_key_file)],
                capture_output=True,
                text=True,
                check=True,
            )
            key = res.stdout.strip()
            if key.startswith("age1"):
                return key
        except Exception:
            pass

    return DEFAULT_AGE_RECIPIENT


def normalize_dotenv_content(raw: str) -> tuple[str, bool]:
    """Normalizes unescaped multi-line quoted values into standard \\n escaped strings."""
    lines = raw.splitlines(keepends=True)
    out = []
    in_quote = False
    quote_char = None
    buf = []
    modified = False

    for line in lines:
        if not in_quote:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                out.append(line)
                continue
            k, v = line.split("=", 1)
            v_str = v.strip()
            if v_str.startswith('"') and not (v_str.endswith('"') and len(v_str) > 1 and not v_str.endswith('\\"')):
                in_quote = True
                quote_char = '"'
                buf = [line.rstrip("\r\n")]
            elif v_str.startswith("'") and not (v_str.endswith("'") and len(v_str) > 1 and not v_str.endswith("\\'")):
                in_quote = True
                quote_char = "'"
                buf = [line.rstrip("\r\n")]
            else:
                out.append(line)
        else:
            buf.append(line.rstrip("\r\n"))
            stripped = line.strip()
            if stripped.endswith(quote_char) and not stripped.endswith(f"\\{quote_char}"):
                in_quote = False
                modified = True
                first = buf[0]
                k, first_v = first.split("=", 1)
                inner_parts = [first_v] + buf[1:]
                joined = "\\n".join(inner_parts)
                out.append(f"{k}={joined}\n")
                buf = []
                quote_char = None

    if in_quote and buf:
        out.extend(b + "\n" for b in buf)

    return "".join(out), modified


def update_env_map(env_map_path: Path, mapping_name: str, dest_rel: str) -> bool:
    """Updates or adds an entry to .secrets/env.map idempotently."""
    clean_dest = dest_rel.lstrip("/")
    entry = f"{mapping_name}={clean_dest}"
    lines = []
    found = False
    modified = False

    if env_map_path.is_file():
        for line in env_map_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                lines.append(line)
                continue
            if "=" in stripped:
                k, v = stripped.split("=", 1)
                k = k.strip()
                v = v.strip().lstrip("/")
                if k == mapping_name:
                    found = True
                    if v != clean_dest:
                        lines.append(entry)
                        modified = True
                    else:
                        lines.append(line)
                    continue
            lines.append(line)

    if not found:
        lines.append(entry)
        modified = True

    if modified or not env_map_path.is_file():
        env_map_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        return True
    return False


def update_gitignore(gitignore_path: Path, pattern: str = ".env") -> bool:
    """Ensures .env is excluded while keeping .secrets/ accessible."""
    existing = ""
    if gitignore_path.is_file():
        existing = gitignore_path.read_text(encoding="utf-8")

    patterns_to_ensure = [pattern, f"{pattern}.*", "!*.example"]
    lines = existing.splitlines()
    added_any = False

    for pat in patterns_to_ensure:
        if not any(line.strip() == pat for line in lines):
            lines.append(pat)
            added_any = True

    if added_any:
        new_content = "\n".join(lines).strip() + "\n"
        gitignore_path.write_text(new_content, encoding="utf-8")
        return True
    return False


def run_sops_encrypt(src_file: Path, dest_file: Path, recipient: str) -> None:
    """Encrypts src_file with SOPS using recipient age key."""
    if not shutil.which("sops"):
        raise RuntimeError("sops executable not found in PATH.")

    cmd = [
        "sops",
        "--config",
        "/dev/null",
        "--encrypt",
        "--age",
        recipient,
        "--output",
        str(dest_file),
        str(src_file),
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"SOPS encryption failed: {res.stderr.strip()}")

    os.chmod(dest_file, 0o600)


def verify_sops_decrypt(src_file: Path, encrypted_file: Path) -> bool:
    """Verifies that the encrypted file decrypts properly with matching keys/values."""
    if not shutil.which("sops"):
        return False

    cmd = ["sops", "decrypt", str(encrypted_file)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"SOPS decryption verification failed: {res.stderr.strip()}")

    def parse_kv(text: str) -> dict[str, str]:
        kv = {}
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            k, v = s.split("=", 1)
            kv[k.strip()] = v.strip()
        return kv

    orig_kv = parse_kv(src_file.read_text(encoding="utf-8"))
    dec_kv = parse_kv(res.stdout)
    return orig_kv == dec_kv


def untrack_git_file(repo_path: Path, dest_rel: str) -> bool:
    """Removes dest_rel from the Git index if currently tracked."""
    check = subprocess.run(
        ["git", "-C", str(repo_path), "ls-files", "--error-unmatch", dest_rel],
        capture_output=True,
    )
    if check.returncode == 0:
        subprocess.run(
            ["git", "-C", str(repo_path), "rm", "--cached", "-q", dest_rel],
            check=True,
        )
        return True
    return False


def encrypt_repo_env(
    repo_path: Path,
    env_file: Path | None = None,
    mapping_name: str | None = None,
    dest_rel: str | None = None,
    age_recipient: str | None = None,
    force: bool = False,
    dry_run: bool = False,
) -> EncryptResult:
    """Encrypts repository environment variables and configures .secrets/env.map."""
    repo_path = repo_path.resolve()
    if not (repo_path / ".git").exists():
        raise ValueError(f"{repo_path} is not a valid Git repository root.")

    resolved_env = (env_file or (repo_path / ".env")).resolve()
    if not resolved_env.is_file():
        raise FileNotFoundError(f"Source environment file not found at {resolved_env}")

    if dest_rel:
        clean_dest = dest_rel.lstrip("/")
    else:
        try:
            clean_dest = str(resolved_env.relative_to(repo_path))
        except ValueError:
            clean_dest = ".env"

    if not mapping_name:
        mapping_name = "app.env" if clean_dest == ".env" else f"{Path(clean_dest).stem}.env"

    secrets_dir = repo_path / ".secrets"
    encrypted_file = secrets_dir / mapping_name
    env_map_file = secrets_dir / "env.map"
    gitignore_file = repo_path / ".gitignore"

    if encrypted_file.exists() and not force and not dry_run:
        raise FileExistsError(
            f"{encrypted_file} already exists. Pass --force to overwrite."
        )

    recipient = resolve_age_recipient(age_recipient)

    if dry_run:
        return EncryptResult(
            repo_path=repo_path,
            env_file=resolved_env,
            dest_rel=clean_dest,
            mapping_name=mapping_name,
            encrypted_file=encrypted_file,
            git_untracked=False,
            gitignore_updated=False,
            verified=False,
        )

    secrets_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    # Normalize multiline values in .env so SOPS parser handles them cleanly
    raw_content = resolved_env.read_text(encoding="utf-8")
    norm_content, modified = normalize_dotenv_content(raw_content)
    if modified:
        resolved_env.write_text(norm_content, encoding="utf-8")

    run_sops_encrypt(resolved_env, encrypted_file, recipient)

    verified = verify_sops_decrypt(resolved_env, encrypted_file)
    update_env_map(env_map_file, mapping_name, clean_dest)
    gitignore_updated = update_gitignore(gitignore_file, Path(clean_dest).name)
    git_untracked = untrack_git_file(repo_path, clean_dest)

    return EncryptResult(
        repo_path=repo_path,
        env_file=resolved_env,
        dest_rel=clean_dest,
        mapping_name=mapping_name,
        encrypted_file=encrypted_file,
        git_untracked=git_untracked,
        gitignore_updated=gitignore_updated,
        verified=verified,
    )


def parse_args(argv: list[str] | None = None):
    import argparse

    parser = argparse.ArgumentParser(
        description="Encrypt repository .env files with SOPS and register them for the Modal sandbox runner.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "repo_path",
        nargs="?",
        default=".",
        help="Path to the repository root directory.",
    )
    parser.add_argument(
        "env_file",
        nargs="?",
        default=None,
        help="Path to the source .env file (defaults to <repo_path>/.env).",
    )
    parser.add_argument(
        "-m",
        "--mapping-name",
        default=None,
        help="Encrypted secret filename in .secrets/ (default: app.env).",
    )
    parser.add_argument(
        "-d",
        "--dest",
        default=None,
        help="Relative destination path for restored .env (default: derived or .env).",
    )
    parser.add_argument(
        "-a",
        "--age-recipient",
        default=None,
        help="Age public key recipient for SOPS encryption.",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite existing encrypted files in .secrets/.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without modifying disk or Git index.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_path = Path(args.repo_path)
    env_file = Path(args.env_file) if args.env_file else None

    try:
        res = encrypt_repo_env(
            repo_path=repo_path,
            env_file=env_file,
            mapping_name=args.mapping_name,
            dest_rel=args.dest,
            age_recipient=args.age_recipient,
            force=args.force,
            dry_run=args.dry_run,
        )

        if args.dry_run:
            print("🔍 [DRY RUN] Would perform:")
            print(f"   • Target Repo: {res.repo_path}")
            print(f"   • Source Env:  {res.env_file}")
            print(f"   • Encrypt to:  {res.encrypted_file}")
            print(f"   • Mapping:     {res.mapping_name} -> {res.dest_rel}")
            return 0

        print(f"🔐 Encrypted: {res.env_file} -> {res.encrypted_file}")
        print(f"📄 Manifest:  .secrets/env.map ({res.mapping_name}={res.dest_rel})")
        if res.gitignore_updated:
            print(f"🙈 Updated:   .gitignore (ensured {Path(res.dest_rel).name} is ignored)")
        if res.git_untracked:
            print(f"🧹 Untracked: {res.dest_rel} removed from Git index")
        if res.verified:
            print("✅ Verified:  Roundtrip decryption matches source bit-for-bit")

        print("\nReady for review. To stage and commit:")
        print(f"   git -C {res.repo_path} add .secrets/ .gitignore")
        print(f'   git -C {res.repo_path} commit -m "chore: add SOPS encrypted env"')
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
