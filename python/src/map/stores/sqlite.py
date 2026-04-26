"""SQLiteLedgerStore — sync persistence via stdlib `sqlite3`.

Per DESIGN.md §2: sync at v0.1, the only I/O hop in the store. v0.2 will
ship a sibling `AsyncSQLiteStore` using `aiosqlite`; the schema and SQL
remain identical.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from ..core.action import LedgerEntry, LedgerEntryStatus
from ..exceptions import StoreError

logger = logging.getLogger("map.stores.sqlite")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ledger_entries (
  id            TEXT PRIMARY KEY,
  sequence      INTEGER NOT NULL UNIQUE,
  timestamp     TEXT NOT NULL,
  payload       TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'ACTIVE'
);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_sequence ON ledger_entries(sequence);
"""


class SQLiteLedgerStore:
    """File-backed (or in-memory) sync store for `Ledger`.

    Construct with a path (file) or ``":memory:"`` (in-process). The
    payload column is JSON — the entry is stored canonically so it can be
    re-hashed identically on read.
    """

    def __init__(self, path: str | Path = "map.db") -> None:
        self._path = str(path)
        self._conn: sqlite3.Connection | None = None
        # Python's sqlite3 enforces "connection used only on its creation
        # thread" by default. MAP is sync at v0.1 but FastAPI users will
        # run the sync `Map` from `asyncio.to_thread()` worker threads, so
        # we disable that check and serialize all access via this lock.
        # SQLite itself is thread-safe in default builds; only the cpython
        # wrapper's check is conservative.
        self._lock = threading.RLock()
        self._open()

    # ─── Connection management ─────────────────────────────────────────────

    def _open(self) -> None:
        try:
            self._conn = sqlite3.connect(
                self._path,
                isolation_level=None,
                check_same_thread=False,
            )
        except sqlite3.Error as e:
            raise StoreError(f"failed to open SQLite at {self._path!r}: {e}") from e
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> SQLiteLedgerStore:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    @property
    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise StoreError("store is closed")
        return self._conn

    # ─── LedgerStore Protocol ──────────────────────────────────────────────

    def append(self, entry: LedgerEntry) -> None:
        payload = json.dumps(entry.model_dump(by_alias=True, exclude_none=True))
        with self._lock:
            try:
                self._db.execute(
                    "INSERT INTO ledger_entries (id, sequence, timestamp, payload, status) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (entry.id, entry.sequence, entry.timestamp, payload, entry.status),
                )
            except sqlite3.IntegrityError as e:
                raise StoreError(
                    f"failed to append entry {entry.id} at sequence {entry.sequence}: {e}"
                ) from e

    def get_entries(self) -> list[LedgerEntry]:
        with self._lock:
            rows = self._db.execute(
                "SELECT payload, status FROM ledger_entries ORDER BY sequence ASC"
            ).fetchall()
        return [_load(payload, status) for (payload, status) in rows]

    def get_entry(self, entry_id: str) -> LedgerEntry | None:
        with self._lock:
            row = self._db.execute(
                "SELECT payload, status FROM ledger_entries WHERE id = ?",
                (entry_id,),
            ).fetchone()
        if row is None:
            return None
        return _load(row[0], row[1])

    def update_status(self, entry_id: str, status: LedgerEntryStatus) -> None:
        with self._lock:
            cursor = self._db.execute(
                "UPDATE ledger_entries SET status = ? WHERE id = ?",
                (status, entry_id),
            )
            if cursor.rowcount == 0:
                raise StoreError(f"no entry with id {entry_id} to update")

    def clear(self) -> None:
        with self._lock:
            self._db.execute("DELETE FROM ledger_entries")


def _load(payload: str, status: str) -> LedgerEntry:
    data = json.loads(payload)
    data["status"] = status  # status column is authoritative for transitions
    return LedgerEntry.model_validate(data)


__all__ = ["SQLiteLedgerStore"]
