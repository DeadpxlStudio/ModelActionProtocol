"""In-memory ledger store.

Default for tests, notebooks, and ephemeral sessions. Not persistent — entries
are lost when the process exits.

Sync per DESIGN.md §2; v0.2 will ship `AsyncMemoryStore` as a sibling.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..core.action import LedgerEntry, LedgerEntryStatus


@runtime_checkable
class LedgerStore(Protocol):
    """Persistence interface for ledger entries.

    All methods are sync. v0.2 adds a sibling ``AsyncLedgerStore`` Protocol;
    sync remains supported indefinitely.
    """

    def append(self, entry: LedgerEntry) -> None: ...

    def get_entries(self) -> list[LedgerEntry]: ...

    def get_entry(self, entry_id: str) -> LedgerEntry | None: ...

    def update_status(
        self, entry_id: str, status: LedgerEntryStatus
    ) -> None: ...

    def clear(self) -> None: ...


class MemoryStore:
    """In-memory implementation of `LedgerStore`."""

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []

    def append(self, entry: LedgerEntry) -> None:
        self._entries.append(entry)

    def get_entries(self) -> list[LedgerEntry]:
        return list(self._entries)

    def get_entry(self, entry_id: str) -> LedgerEntry | None:
        for e in self._entries:
            if e.id == entry_id:
                return e
        return None

    def update_status(
        self, entry_id: str, status: LedgerEntryStatus
    ) -> None:
        for i, e in enumerate(self._entries):
            if e.id == entry_id:
                self._entries[i] = e.model_copy(update={"status": status})
                return

    def clear(self) -> None:
        self._entries = []


__all__ = ["LedgerStore", "MemoryStore"]
