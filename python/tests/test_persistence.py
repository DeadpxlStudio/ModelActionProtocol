"""Persistence tests — SQLite and Postgres stores.

Postgres tests are gated on `DB_HOST` (mirrors the TS pattern). They run
in CI when the secret is set; otherwise they're skipped cleanly.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from map import Action, CriticResult, Ledger, MemoryStore, verify_chain
from map.stores.sqlite import SQLiteLedgerStore


def _entry_dict(entry: Any) -> dict[str, Any]:
    return entry.model_dump(by_alias=True, exclude_none=True)


def _populate(ledger: Ledger, n: int = 3) -> None:
    for i in range(n):
        ledger.append(
            Action(tool="step", input={"i": i}, output={"i": i}),
            {"v": i},
            {"v": i + 1},
            CriticResult(verdict="PASS", reason="ok"),
        )


# ─── SQLite ─────────────────────────────────────────────────────────────────


def test_sqlite_round_trips_ledger_unchanged() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "ledger.db"
        store1 = SQLiteLedgerStore(path)
        ledger1 = Ledger(store=store1)
        _populate(ledger1, 4)

        # Capture the original entries before closing.
        original = [_entry_dict(e) for e in ledger1.get_entries()]
        store1.close()

        # Reopen — entries persist across process lifetime.
        store2 = SQLiteLedgerStore(path)
        ledger2 = Ledger.load(store=store2)
        loaded = [_entry_dict(e) for e in ledger2.get_entries()]
        store2.close()

        assert loaded == original
        # Most importantly: the chain still verifies after the round-trip.
        assert verify_chain(loaded) == {"valid": True}


def test_sqlite_in_memory_works() -> None:
    store = SQLiteLedgerStore(":memory:")
    try:
        ledger = Ledger(store=store)
        _populate(ledger, 2)
        assert len(ledger.get_entries()) == 2
        assert verify_chain([_entry_dict(e) for e in ledger.get_entries()]) == {"valid": True}
    finally:
        store.close()


def test_sqlite_unique_sequence_constraint() -> None:
    """Two entries with the same sequence in the same store must conflict.

    The Ledger increments sequence atomically; this test exercises the store
    directly with a duplicated sequence to confirm the UNIQUE constraint.
    """
    from map.exceptions import StoreError

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "dup.db"
        store = SQLiteLedgerStore(path)
        try:
            ledger = Ledger(store=store)
            entry = ledger.append(
                Action(tool="x", input={}, output=None),
                None,
                None,
                CriticResult(verdict="PASS", reason="ok"),
            )
            # Try to write a second entry with the same sequence directly
            # via the store — this simulates a buggy parallel writer.
            duplicate = entry.model_copy(update={"id": "00000000-0000-4000-8000-000000000000"})
            with pytest.raises(StoreError):
                store.append(duplicate)
        finally:
            store.close()


def test_sqlite_status_update_persists() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "rb.db"
        store = SQLiteLedgerStore(path)
        try:
            ledger = Ledger(store=store)
            entry = ledger.append(
                Action(tool="x", input={}, output=None),
                None,
                None,
                CriticResult(verdict="PASS", reason="ok"),
            )
            ledger.rollback_to(entry.id)
            store.close()

            # Reopen and check status persisted.
            store2 = SQLiteLedgerStore(path)
            try:
                reloaded = SQLiteLedgerStore(path).get_entry(entry.id)
                assert reloaded is not None
                assert reloaded.status == "ROLLED_BACK"
            finally:
                store2.close()
        finally:
            try:
                store.close()
            except Exception:
                pass


# ─── Postgres (gated on DB_HOST) ────────────────────────────────────────────

postgres = pytest.importorskip(
    "psycopg",
    reason="psycopg not installed; install map-protocol[postgres] to run",
)


@pytest.mark.postgres
@pytest.mark.skipif("DB_HOST" not in os.environ, reason="DB_HOST not set")
def test_postgres_round_trips_ledger() -> None:
    from map.stores.postgres import PostgresLedgerStore

    conninfo = (
        f"host={os.environ['DB_HOST']} "
        f"user={os.environ.get('DB_USER', 'postgres')} "
        f"password={os.environ.get('DB_PASSWORD', '')} "
        f"dbname={os.environ.get('DB_NAME', 'postgres')}"
    )
    store = PostgresLedgerStore(conninfo=conninfo, session_id="test-session-1")
    try:
        store.init()
        store.clear()
        ledger = Ledger(store=store)
        _populate(ledger, 3)
        loaded = [_entry_dict(e) for e in store.get_entries()]
        assert verify_chain(loaded) == {"valid": True}
    finally:
        store.clear()
        store.close()
