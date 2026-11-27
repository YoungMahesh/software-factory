"""Per-record JSON state persistence backed by Modal Volume `factory-state-v1`."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import threading
from typing import Any, Callable, TypeVar

import modal
from pydantic import BaseModel

from ._coordination import StateTransitions
from ._github_repos import RepositoryCatalogCache
from ._models import FactoryAppRecord, LaunchRequestRecord, PrimeSandboxRecord, derive_app_slug, utc_now_iso
from sandbox.dashboard_self_deploy import DashboardDeployStateMixin
from sandbox.docs_deploy import DocsDeployStateMixin
from ._scratchpad_cache import (
    CachedScratchpadNote,
    ScratchpadCatalogCache,
    ScratchpadSection,
    apply_scratchpad_body,
    apply_scratchpad_commit,
    apply_scratchpad_delete,
    merge_refreshed_scratchpad_catalog,
)

logger = logging.getLogger(__name__)

FACTORY_STATE_VOLUME_NAME = "factory-state-v1"
FACTORY_STATE_MOUNT_PATH = "/root/.factory-state"
LOCAL_STATE_FALLBACK_DIR = Path.home() / ".modal" / "factory-state"

_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_TModel = TypeVar("_TModel", bound=BaseModel)

_LOCKS_GUARD = threading.Lock()
_TARGET_LOCKS: dict[str, threading.RLock] = {}


def _get_lock_for_target(volume: Any | None, root_dir: Path) -> threading.RLock:
    """Returns a process-wide reentrant lock shared across stores targeting the same backend."""
    key = f"vol:{id(volume)}" if volume is not None else f"dir:{root_dir.resolve()}"
    with _LOCKS_GUARD:
        lock = _TARGET_LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _TARGET_LOCKS[key] = lock
        return lock


def get_factory_state_volume(name: str = FACTORY_STATE_VOLUME_NAME) -> modal.Volume:
    """Returns the persistent Modal Volume handle for Factory App metadata."""
    return modal.Volume.from_name(name, create_if_missing=True)


class FactoryStateStore(StateTransitions, DashboardDeployStateMixin, DocsDeployStateMixin):
    """Thread-safe per-record JSON persistence for Factory Apps and Launch Requests."""

    def __init__(
        self,
        root_dir: Path | str | None = None,
        volume: Any | None = None,
    ) -> None:
        if root_dir is not None:
            self.root_dir = Path(root_dir)
        elif os.environ.get("FACTORY_STATE_DIR"):
            self.root_dir = Path(os.environ["FACTORY_STATE_DIR"])
        elif Path(FACTORY_STATE_MOUNT_PATH).is_dir():
            self.root_dir = Path(FACTORY_STATE_MOUNT_PATH)
        else:
            self.root_dir = LOCAL_STATE_FALLBACK_DIR

        if volume is not None:
            self.volume = volume
        elif self.root_dir == Path(FACTORY_STATE_MOUNT_PATH):
            try:
                self.volume = get_factory_state_volume()
            except Exception as exc:
                logger.debug("Could not bind factory-state volume: %s", exc)
                self.volume = None
        else:
            self.volume = None

        self.apps_dir = self.root_dir / "apps"
        self.launches_dir = self.root_dir / "launches"
        self.primes_dir = self.root_dir / "primes"
        self.github_repos_path = self.root_dir / "github-repos.json"
        self.scratchpad_catalog_path = self.root_dir / "scratchpad-catalog.json"
        self._lock = _get_lock_for_target(self.volume, self.root_dir)

    def _reload_volume(self) -> None:
        if self.volume is not None and hasattr(self.volume, "reload"):
            self.volume.reload()

    def _commit_volume(self) -> None:
        if self.volume is not None and hasattr(self.volume, "commit"):
            self.volume.commit()

    def _ensure_dirs(self) -> None:
        self.apps_dir.mkdir(parents=True, exist_ok=True)
        self.launches_dir.mkdir(parents=True, exist_ok=True)
        self.primes_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _validate_id(record_id: str) -> str:
        if not record_id or not _ID_PATTERN.fullmatch(record_id):
            raise ValueError(f"Invalid record identifier: {record_id!r}")
        return record_id

    def _app_path(self, app_id: str) -> Path:
        return self.apps_dir / f"{self._validate_id(app_id)}.json"

    def _launch_path(self, request_id: str) -> Path:
        return self.launches_dir / f"{self._validate_id(request_id)}.json"

    def _prime_path(self, prime_key: str) -> Path:
        return self.primes_dir / f"{self._validate_id(prime_key)}.json"

    @staticmethod
    def _write_model_file(path: Path, model: BaseModel) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f"{path.name}.tmp.{os.getpid()}.{threading.get_ident()}")
        tmp_path.write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_path, path)

    @staticmethod
    def _read_model_file(path: Path, model_cls: type[_TModel]) -> _TModel | None:
        if not path.is_file():
            return None
        try:
            return model_cls.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Failed parsing factory state file {path}") from exc

    def _save_record(self, path: Path, record: _TModel) -> _TModel:
        with self._lock:
            self._ensure_dirs()
            updated = record.model_copy(update={"updated_at": utc_now_iso()})
            self._write_model_file(path, updated)
            self._commit_volume()
            return updated

    def _get_record(self, path: Path, model_cls: type[_TModel], *, reload: bool = True) -> _TModel | None:
        with self._lock:
            if reload:
                self._reload_volume()
            return self._read_model_file(path, model_cls)

    def _modify_record(
        self,
        path: Path,
        model_cls: type[_TModel],
        fn: Callable[[_TModel], _TModel | None],
        missing_error: str,
    ) -> _TModel | None:
        with self._lock:
            self._reload_volume()
            current = self._read_model_file(path, model_cls)
            if current is None:
                raise KeyError(missing_error)
            updated = fn(current)
            if updated is None:
                return None
            if getattr(updated, "updated_at", None) == getattr(current, "updated_at", None):
                updated = updated.model_copy(update={"updated_at": utc_now_iso()})
            self._write_model_file(path, updated)
            self._commit_volume()
            return updated

    def save_app(self, app: FactoryAppRecord) -> FactoryAppRecord:
        """Persists a FactoryAppRecord and commits the volume."""
        return self._save_record(self._app_path(app.app_id), app)

    def get_app(self, app_id: str, *, reload: bool = True) -> FactoryAppRecord | None:
        """Loads a FactoryAppRecord by ID, returning None if missing or the ID is invalid."""
        try:
            path = self._app_path(app_id)
        except ValueError:
            return None
        return self._get_record(path, FactoryAppRecord, reload=reload)

    def update_app(self, app_id: str, **updates: Any) -> FactoryAppRecord:
        """Reloads, applies field updates to a FactoryAppRecord, and commits."""
        result = self._modify_record(
            self._app_path(app_id),
            FactoryAppRecord,
            lambda cur: cur.model_copy(update={**updates, "updated_at": utc_now_iso()}),
            f"Factory App '{app_id}' not found.",
        )
        assert result is not None
        return result

    def update_app_if_current_request(
        self,
        app_id: str,
        request_id: str,
        **updates: Any,
    ) -> FactoryAppRecord | None:
        """Conditionally updates FactoryAppRecord only when latest_request_id matches request_id."""
        try:
            path = self._app_path(app_id)
        except ValueError:
            return None
        try:
            return self._modify_record(
                path,
                FactoryAppRecord,
                lambda cur: (
                    cur.model_copy(update={**updates, "updated_at": utc_now_iso()})
                    if cur.latest_request_id == request_id
                    else None
                ),
                f"Factory App '{app_id}' not found.",
            )
        except KeyError:
            return None

    def list_apps(self) -> list[FactoryAppRecord]:
        """Lists all FactoryAppRecord entries ordered newest first."""
        with self._lock:
            self._reload_volume()
            if not self.apps_dir.is_dir():
                return []
            items: list[FactoryAppRecord] = []
            for entry in self.apps_dir.glob("*.json"):
                record = self._read_model_file(entry, FactoryAppRecord)
                if record is not None:
                    items.append(record)
            items.sort(key=lambda item: item.created_at, reverse=True)
            return items

    def delete_app(self, app_id: str) -> bool:
        """Deletes a FactoryAppRecord and its associated Launch Request files if present."""
        try:
            path = self._app_path(app_id)
        except ValueError:
            return False
        with self._lock:
            self._reload_volume()
            if not path.is_file():
                return False
            path.unlink()
            if self.launches_dir.is_dir():
                for entry in self.launches_dir.glob("*.json"):
                    launch = self._read_model_file(entry, LaunchRequestRecord)
                    if launch is not None and launch.app_id == app_id:
                        entry.unlink(missing_ok=True)
            self._commit_volume()
            return True

    def save_launch(self, launch: LaunchRequestRecord) -> LaunchRequestRecord:
        """Persists a LaunchRequestRecord and commits the volume."""
        return self._save_record(self._launch_path(launch.request_id), launch)

    def get_launch(self, request_id: str, *, reload: bool = True) -> LaunchRequestRecord | None:
        """Loads a LaunchRequestRecord, scrubbing any expired #token= handoff URL."""
        try:
            path = self._launch_path(request_id)
        except ValueError:
            return None
        with self._lock:
            record = self._get_record(path, LaunchRequestRecord, reload=reload)
            if record is None:
                return None
            scrubbed, changed = record.scrub_expired_handoff()
            if changed:
                scrubbed = scrubbed.model_copy(update={"updated_at": utc_now_iso()})
                self._write_model_file(path, scrubbed)
                self._commit_volume()
            return scrubbed

    def update_launch(self, request_id: str, **updates: Any) -> LaunchRequestRecord:
        """Reloads, applies field updates to a LaunchRequestRecord, and commits."""
        return self.modify_launch(
            request_id,
            lambda cur: cur.model_copy(update={**updates, "updated_at": utc_now_iso()}),
        )

    def modify_launch(
        self,
        request_id: str,
        fn: Callable[[LaunchRequestRecord], LaunchRequestRecord],
    ) -> LaunchRequestRecord:
        """Reloads, transforms a LaunchRequestRecord atomically under the store lock, and commits."""
        result = self._modify_record(
            self._launch_path(request_id),
            LaunchRequestRecord,
            fn,
            f"Launch Request '{request_id}' not found.",
        )
        assert result is not None
        return result

    def create_app_and_launch(
        self,
        app: FactoryAppRecord,
        launch: LaunchRequestRecord,
    ) -> tuple[FactoryAppRecord, LaunchRequestRecord]:
        """Atomically writes a FactoryAppRecord and LaunchRequestRecord before a single commit."""
        with self._lock:
            self._ensure_dirs()
            if self.get_app(app.app_id, reload=False) is None:
                records = (self._read_model_file(path, FactoryAppRecord) for path in self.apps_dir.glob("*.json"))
                slugs = {record.slug for record in records if record is not None}
                app = app.model_copy(update={"slug": derive_app_slug(app.prompt, app.slug, existing_slugs=slugs)})
            now = utc_now_iso()
            saved_app = app.model_copy(update={"updated_at": now})
            saved_launch = launch.model_copy(update={"updated_at": now})
            self._write_model_file(self._app_path(saved_app.app_id), saved_app)
            self._write_model_file(self._launch_path(saved_launch.request_id), saved_launch)
            self._commit_volume()
            return saved_app, saved_launch

    def save_prime(self, prime: PrimeSandboxRecord) -> PrimeSandboxRecord:
        """Persists a PrimeSandboxRecord and commits the volume."""
        return self._save_record(self._prime_path(prime.prime_key), prime)

    def get_prime(self, prime_key: str, *, reload: bool = True) -> PrimeSandboxRecord | None:
        """Loads a PrimeSandboxRecord by compatibility key, returning None if missing or the ID is invalid."""
        try:
            path = self._prime_path(prime_key)
        except ValueError:
            return None
        return self._get_record(path, PrimeSandboxRecord, reload=reload)

    def modify_prime(
        self,
        prime_key: str,
        fn: Callable[[PrimeSandboxRecord | None], PrimeSandboxRecord | None],
    ) -> PrimeSandboxRecord | None:
        """Atomically reloads, transforms (or initializes) a PrimeSandboxRecord, and commits."""
        path = self._prime_path(prime_key)
        with self._lock:
            self._ensure_dirs()
            self._reload_volume()
            current = self._read_model_file(path, PrimeSandboxRecord)
            updated = fn(current)
            if updated is None:
                return None
            if current is None or updated.updated_at == current.updated_at:
                updated = updated.model_copy(update={"updated_at": utc_now_iso()})
            self._write_model_file(path, updated)
            self._commit_volume()
            return updated

    def list_primes(self) -> list[PrimeSandboxRecord]:
        """Lists all PrimeSandboxRecord entries ordered newest updated first."""
        with self._lock:
            self._reload_volume()
            if not self.primes_dir.is_dir():
                return []
            items: list[PrimeSandboxRecord] = []
            for entry in self.primes_dir.glob("*.json"):
                record = self._read_model_file(entry, PrimeSandboxRecord)
                if record is not None:
                    items.append(record)
            items.sort(key=lambda item: item.updated_at, reverse=True)
            return items

    def delete_prime(self, prime_key: str) -> bool:
        """Deletes a PrimeSandboxRecord by compatibility key if present."""
        try:
            path = self._prime_path(prime_key)
        except ValueError:
            return False
        with self._lock:
            self._reload_volume()
            if not path.is_file():
                return False
            path.unlink()
            self._commit_volume()
            return True

    def get_repo_catalog(self, *, reload: bool = True) -> RepositoryCatalogCache:
        """Loads the cached GitHub repository catalog without hitting the GitHub API."""
        catalog = self._get_record(self.github_repos_path, RepositoryCatalogCache, reload=reload)
        return catalog or RepositoryCatalogCache()

    def save_repo_catalog(self, catalog: RepositoryCatalogCache) -> RepositoryCatalogCache:
        """Persists the Repository Catalog Cache to github-repos.json and commits the volume."""
        with self._lock:
            self._ensure_dirs()
            self._write_model_file(self.github_repos_path, catalog)
            self._commit_volume()
            return catalog

    def get_scratchpad_catalog(self, *, reload: bool = True) -> ScratchpadCatalogCache:
        """Loads the cached Scratchpad catalog without querying GitHub."""
        catalog = self._get_record(self.scratchpad_catalog_path, ScratchpadCatalogCache, reload=reload)
        return catalog or ScratchpadCatalogCache()

    def _mutate_scratchpad_catalog(
        self,
        transform: Callable[[ScratchpadCatalogCache], ScratchpadCatalogCache],
    ) -> ScratchpadCatalogCache:
        with self._lock:
            self._reload_volume()
            current = self._read_model_file(self.scratchpad_catalog_path, ScratchpadCatalogCache) or ScratchpadCatalogCache()
            updated = transform(current)
            self._ensure_dirs()
            self._write_model_file(self.scratchpad_catalog_path, updated)
            self._commit_volume()
            return updated

    def save_scratchpad_catalog(
        self,
        config_repo: str,
        refreshed_at: str,
        ideas: list[CachedScratchpadNote],
        raw: list[CachedScratchpadNote],
    ) -> ScratchpadCatalogCache:
        """Persists refreshed Idea/Raw lists while retaining valid matching-SHA body caches."""
        return self._mutate_scratchpad_catalog(
            lambda cur: merge_refreshed_scratchpad_catalog(cur, config_repo, refreshed_at, ideas, raw)
        )

    def record_scratchpad_commit(
        self,
        config_repo: str,
        note: CachedScratchpadNote,
        content: str,
    ) -> ScratchpadCatalogCache:
        """Records a newly committed Idea or Raw note and its body in the Scratchpad Catalog Cache."""
        return self._mutate_scratchpad_catalog(
            lambda cur: apply_scratchpad_commit(cur, config_repo, note, content)
        )

    def cache_scratchpad_body(
        self,
        config_repo: str,
        note: CachedScratchpadNote,
        content: str,
    ) -> ScratchpadCatalogCache:
        """Caches an individual lazily fetched Scratchpad note body."""
        return self._mutate_scratchpad_catalog(
            lambda cur: apply_scratchpad_body(cur, config_repo, note, content)
        )

    def delete_scratchpad_note_cache(
        self,
        config_repo: str,
        section: ScratchpadSection,
        filename: str,
    ) -> ScratchpadCatalogCache:
        """Removes a deleted note summary and cached body from Scratchpad Catalog Cache."""
        return self._mutate_scratchpad_catalog(
            lambda cur: apply_scratchpad_delete(cur, config_repo, section, filename)
        )


_DEFAULT_STORE: FactoryStateStore | None = None
_DEFAULT_STORE_LOCK = threading.Lock()


def get_default_store() -> FactoryStateStore:
    """Returns the shared process-level FactoryStateStore instance."""
    global _DEFAULT_STORE
    with _DEFAULT_STORE_LOCK:
        if _DEFAULT_STORE is None:
            _DEFAULT_STORE = FactoryStateStore()
        return _DEFAULT_STORE


def set_default_store(store: FactoryStateStore | None) -> None:
    """Overrides or resets the process-level FactoryStateStore instance."""
    global _DEFAULT_STORE
    with _DEFAULT_STORE_LOCK:
        _DEFAULT_STORE = store
