"""PostgresLedgerStore — sync persistence via psycopg3.

Per DESIGN.md §2 + §10: sync at v0.1 using ``psycopg[binary]>=3`` in sync
mode. v0.2 will ship a sibling ``AsyncPostgresStore`` using
``psycopg[async]`` — same library, same SQL, same wire format.

Mirrors the TS reference behaviors: session isolation by ``session_id``,
SERIALIZABLE isolation for writes, retry on serialization failures.

Requires the ``[postgres]`` extra::

    pip install "map-protocol[postgres]"
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from ..core.action import LedgerEntry, LedgerEntryStatus
from ..exceptions import StoreError

logger = logging.getLogger("map.stores.postgres")

try:
    import psycopg
    from psycopg import errors as pg_errors
except ImportError as _e:  # pragma: no cover - import guard
    psycopg = None  # type: ignore[assignment]
    pg_errors = None  # type: ignore[assignment]
    _IMPORT_ERROR: ImportError | None = _e
else:
    _IMPORT_ERROR = None


_SCHEMA_PREFIX = """
CREATE TABLE IF NOT EXISTS ledger_entries (
  id            TEXT PRIMARY KEY,
  session_id    TEXT NOT NULL,
  sequence      INTEGER NOT NULL,
  timestamp     TIMESTAMPTZ NOT NULL,
  payload       JSONB NOT NULL,
  status        TEXT NOT NULL DEFAULT 'ACTIVE',
  UNIQUE (session_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_session ON ledger_entries(session_id);
CREATE INDEX IF NOT EXISTS idx_ledger_entries_session_seq ON ledger_entries(session_id, sequence);
"""


class PostgresLedgerStore:
    """Multi-session Postgres store for production use."""

    def __init__(
        self,
        *,
        conninfo: str | None = None,
        session_id: str = "default",
        max_retries: int = 3,
        table_name: str = "ledger_entries",
    ) -> None:
        if psycopg is None:
            raise ImportError(
                "psycopg is not installed. "
                "Install with: pip install 'map-protocol[postgres]'"
            ) from _IMPORT_ERROR
        if not session_id:
            raise ValueError("session_id must be a non-empty string")
        self._conninfo = conninfo
        self._session_id = session_id
        self._max_retries = max_retries
        self._table = table_name
        self._conn: Any = None
        self._open()

    # ─── Connection ────────────────────────────────────────────────────────

    def _open(self) -> None:
        try:
            self._conn = psycopg.connect(self._conninfo, autocommit=False)  # type: ignore[union-attr]
        except Exception as e:
            raise StoreError(f"failed to connect to Postgres: {e}") from e

    def init(self) -> None:
        """Create schema if missing. Idempotent; safe to call repeatedly."""
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA_PREFIX)
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> PostgresLedgerStore:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # ─── LedgerStore Protocol ──────────────────────────────────────────────

    def append(self, entry: LedgerEntry) -> None:
        payload = json.dumps(entry.model_dump(by_alias=True, exclude_none=True))
        sql = (
            f"INSERT INTO {self._table} "
            "(id, session_id, sequence, timestamp, payload, status) "
            "VALUES (%s, %s, %s, %s, %s::jsonb, %s)"
        )
        self._with_retry(
            sql,
            (entry.id, self._session_id, entry.sequence, entry.timestamp, payload, entry.status),
        )

    def get_entries(self) -> list[LedgerEntry]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT payload, status FROM {self._table} "
                "WHERE session_id = %s ORDER BY sequence ASC",
                (self._session_id,),
            )
            rows = cur.fetchall()
        return [_load(payload, status) for (payload, status) in rows]

    def get_entry(self, entry_id: str) -> LedgerEntry | None:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT payload, status FROM {self._table} "
                "WHERE session_id = %s AND id = %s",
                (self._session_id, entry_id),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return _load(row[0], row[1])

    def update_status(self, entry_id: str, status: LedgerEntryStatus) -> None:
        sql = (
            f"UPDATE {self._table} SET status = %s "
            "WHERE session_id = %s AND id = %s"
        )
        self._with_retry(sql, (status, self._session_id, entry_id))

    def clear(self) -> None:
        sql = f"DELETE FROM {self._table} WHERE session_id = %s"
        self._with_retry(sql, (self._session_id,))

    # ─── Internals ─────────────────────────────────────────────────────────

    def _with_retry(self, sql: str, params: tuple[Any, ...]) -> None:
        """Run a write under SERIALIZABLE with bounded retry on conflict."""
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                with self._conn.transaction():
                    self._conn.set_isolation_level(  # type: ignore[attr-defined]
                        psycopg.IsolationLevel.SERIALIZABLE  # type: ignore[union-attr]
                    )
                    with self._conn.cursor() as cur:
                        cur.execute(sql, params)
                return
            except Exception as e:  # broad: psycopg raises a family of subclasses
                last_exc = e
                if pg_errors is not None and isinstance(
                    e, pg_errors.SerializationFailure
                ):
                    backoff = 0.05 * (2**attempt)
                    logger.debug(
                        "serialization failure, retrying in %.3fs (attempt %d/%d)",
                        backoff,
                        attempt + 1,
                        self._max_retries,
                    )
                    time.sleep(backoff)
                    continue
                raise StoreError(f"Postgres write failed: {e}") from e
        raise StoreError(
            f"Postgres write retried {self._max_retries} times: {last_exc}"
        ) from last_exc


def _load(payload: Any, status: str) -> LedgerEntry:
    data = payload if isinstance(payload, dict) else json.loads(payload)
    data["status"] = status
    return LedgerEntry.model_validate(data)


__all__ = ["PostgresLedgerStore"]
