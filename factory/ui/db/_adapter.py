"""Database adapter and environment loading helpers for Factory Studio."""

import os
from pathlib import Path
from typing import Any


def _load_env_file(env_file: str | Path | None = None) -> None:
    """Loads environment variables from a .env file into os.environ if not already set."""
    if env_file is not None:
        target = Path(env_file)
    else:
        target = Path.cwd() / ".env"
        if not target.is_file():
            # Search parent directories for root .env
            for parent in Path(__file__).resolve().parents:
                candidate = parent / ".env"
                if candidate.is_file():
                    target = candidate
                    break

    if target.is_file():
        try:
            with open(target, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            pass


class _LibsqlRow:
    """Row adapter for libsql query results providing dict-like and index-based access."""

    __slots__ = ("_values", "_mapping", "_ci_mapping")

    def __init__(self, description: tuple, values: tuple):
        self._values = values
        self._mapping = {col[0]: val for col, val in zip(description, values)}
        self._ci_mapping = {col[0].lower(): val for col, val in zip(description, values)}

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, (int, slice)):
            return self._values[key]
        if key in self._mapping:
            return self._mapping[key]
        lower_key = str(key).lower()
        if lower_key in self._ci_mapping:
            return self._ci_mapping[lower_key]
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key in self._mapping:
            return self._mapping[key]
        return self._ci_mapping.get(str(key).lower(), default)

    def keys(self):
        return self._mapping.keys()

    def values(self):
        return self._values

    def items(self):
        return self._mapping.items()

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return f"<LibsqlRow {self._mapping}>"


class _LibsqlCursorAdapter:
    """Cursor wrapper that converts returned tuples into LibsqlRow objects."""

    def __init__(self, raw_cursor: Any):
        self._cur = raw_cursor

    def execute(self, sql: str, params: tuple | list | dict = ()):
        return self._cur.execute(sql, params)

    def executemany(self, sql: str, params_seq: Any):
        return self._cur.executemany(sql, params_seq)

    def fetchone(self) -> _LibsqlRow | None:
        val = self._cur.fetchone()
        if val is None:
            return None
        return _LibsqlRow(self._cur.description, val)

    def fetchall(self) -> list[_LibsqlRow]:
        desc = self._cur.description
        return [_LibsqlRow(desc, val) for val in self._cur.fetchall()]

    def close(self) -> None:
        self._cur.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cur, name)
