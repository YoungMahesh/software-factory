"""Central Config Store (caddy/) deep module interface."""

from ._cli import maybe_sync_after_deploy, run_caddy_store_subcommand
from ._compose_filter import DEFAULT_CADDY_NETWORK, filter_compose_override_networks
from ._github import (
    CADDY_STORE_PREFIX,
    CANONICAL_CADDY_STORE_REPO,
    CANONICAL_CONFIG_REPO,
    DEFAULT_CADDY_STORE_PROFILE,
    commit_caddy_store_file,
    delete_caddy_store_file,
    ensure_caddy_store_repo,
    fetch_caddy_store_bundle,
    git_blob_sha,
    is_declarative_caddy_relpath,
    list_caddy_store_profile_blobs,
)
from ._sync import (
    CaddyStoreResult,
    backup_caddy_to_store,
    resolve_caddy_store_profile,
    restore_caddy_from_store,
)
from ._vps import (
    DEFAULT_CADDY_DIR,
    fetch_vps_caddy_files,
    list_remote_docker_networks,
    read_local_caddy_dir,
    write_local_caddy_dir,
)

__all__ = [
    "CADDY_STORE_PREFIX",
    "CANONICAL_CADDY_STORE_REPO",
    "CANONICAL_CONFIG_REPO",
    "CaddyStoreResult",
    "DEFAULT_CADDY_DIR",
    "DEFAULT_CADDY_NETWORK",
    "DEFAULT_CADDY_STORE_PROFILE",
    "backup_caddy_to_store",
    "commit_caddy_store_file",
    "delete_caddy_store_file",
    "ensure_caddy_store_repo",
    "fetch_caddy_store_bundle",
    "fetch_vps_caddy_files",
    "filter_compose_override_networks",
    "git_blob_sha",
    "is_declarative_caddy_relpath",
    "list_caddy_store_profile_blobs",
    "list_remote_docker_networks",
    "maybe_sync_after_deploy",
    "read_local_caddy_dir",
    "resolve_caddy_store_profile",
    "restore_caddy_from_store",
    "run_caddy_store_subcommand",
    "write_local_caddy_dir",
]
