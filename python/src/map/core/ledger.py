"""Append-only cryptographic action log (sync).

Per DESIGN.md §2: this module is part of the pure-CPU + store-only-I/O
core. Everything that isn't a `store.*` call must remain synchronous and
side-effect-free. The v0.2 async retrofit will swap the store for an
`AsyncLedgerStore` and provide an `AsyncMap` orchestrator; this module's
shape will be reused.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from ..exceptions import EntryNotFound
from .._version import SPEC_VERSION
from .action import (
    Action,
    CriticResult,
    LedgerEntry,
    LedgerExport,
    LedgerSnapshots,
    LedgerStats,
    to_jsonable,
)
from .snapshot import GENESIS_HASH, capture_snapshot, compute_entry_hash

logger = logging.getLogger("map.ledger")

MapEvent = dict[str, Any]
MapEventHandler = Callable[[MapEvent], None]


class Ledger:
    """The append-only ledger that backs every MAP session."""

    def __init__(self, store: Any | None = None) -> None:
        # Lazy import to avoid circular: stores.memory imports from action.
        from ..stores.memory import MemoryStore

        self._entries: list[LedgerEntry] = []
        self._listeners: list[MapEventHandler] = []
        self._store = store if store is not None else MemoryStore()

    @classmethod
    def load(cls, store: Any | None = None) -> Ledger:
        ledger = cls(store=store)
        ledger.init()
        return ledger

    def init(self) -> None:
        self._entries = self._store.get_entries()

    def on(self, handler: MapEventHandler) -> Callable[[], None]:
        self._listeners.append(handler)

        def unsub() -> None:
            try:
                self._listeners.remove(handler)
            except ValueError:
                pass

        return unsub

    def _emit(self, event: MapEvent) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                # A broken listener must never corrupt the ledger.
                logger.exception("ledger event listener raised; ignoring")

    def append(
        self,
        action: Action,
        state_before_value: Any,
        state_after_value: Any,
        critic: CriticResult,
    ) -> LedgerEntry:
        sequence = len(self._entries)
        parent_hash = self._entries[-1].hash if sequence > 0 else GENESIS_HASH

        before_clone, before_hash = capture_snapshot(state_before_value)
        after_clone, after_hash = capture_snapshot(state_after_value)

        action_dump = to_jsonable(action)
        critic_dump = to_jsonable(critic)

        entry_hash = compute_entry_hash(
            sequence=sequence,
            action=action_dump,
            state_before=before_hash,
            state_after=after_hash,
            parent_hash=parent_hash,
            critic=critic_dump,
        )

        entry = LedgerEntry(
            id=str(uuid.uuid4()),
            sequence=sequence,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            action=action,
            stateBefore=before_hash,
            stateAfter=after_hash,
            snapshots=LedgerSnapshots(before=before_clone, after=after_clone),
            parentHash=parent_hash,
            hash=entry_hash,
            critic=critic,
        )

        # Persist to the store FIRST. If this fails, leave the in-memory
        # cache untouched — the contract is that a failed append is a
        # no-op visible to callers, not a torn state where the cache and
        # disk disagree.
        self._store.append(entry)
        self._entries.append(entry)

        self._emit({"type": "action:complete", "entry": entry})
        self._emit({"type": "critic:verdict", "entry": entry})

        if critic.verdict == "FLAGGED":
            self._emit({"type": "flagged", "entry": entry})

        return entry

    def rollback_to(self, target_id: str) -> dict[str, Any]:
        target_idx = next(
            (i for i, e in enumerate(self._entries) if e.id == target_id), -1
        )
        if target_idx == -1:
            raise EntryNotFound(f"Ledger entry {target_id} not found")

        target = self._entries[target_idx]
        self._emit({"type": "rollback:start", "targetId": target_id})

        reverted = 0
        for i in range(target_idx, len(self._entries)):
            if self._entries[i].status != "ROLLED_BACK":
                self._entries[i] = self._entries[i].model_copy(
                    update={"status": "ROLLED_BACK"}
                )
                self._store.update_status(self._entries[i].id, "ROLLED_BACK")
                reverted += 1

        last_committed = next(
            (
                e
                for e in reversed(self._entries)
                if e.status == "ACTIVE" and e.action.tool != "ROLLBACK"
            ),
            None,
        )
        current_state = (
            last_committed.snapshots.after
            if last_committed
            else target.snapshots.before
        )

        rollback_action = Action(
            tool="ROLLBACK",
            input={"targetId": target_id, "targetSequence": target.sequence},
            output={"entriesReverted": reverted, "restoredToHash": target.stateBefore},
        )

        self.append(
            rollback_action,
            current_state,
            target.snapshots.before,
            CriticResult(
                verdict="PASS",
                reason=f"Rollback to entry {target.sequence}",
            ),
        )

        self._emit(
            {
                "type": "rollback:complete",
                "targetId": target_id,
                "entriesReverted": reverted,
            }
        )

        return {"state": target.snapshots.before, "entriesReverted": reverted}

    def get_entries(self) -> list[LedgerEntry]:
        return list(self._entries)

    def get_committed_entries(self) -> list[LedgerEntry]:
        return [e for e in self._entries if e.status == "ACTIVE"]

    def get_entry(self, entry_id: str) -> LedgerEntry | None:
        return next((e for e in self._entries if e.id == entry_id), None)

    def get_stats(self) -> LedgerStats:
        return LedgerStats(
            total=len(self._entries),
            committed=sum(
                1
                for e in self._entries
                if e.status == "ACTIVE" and e.action.tool != "ROLLBACK"
            ),
            rolledBack=sum(1 for e in self._entries if e.status == "ROLLED_BACK"),
            corrections=sum(1 for e in self._entries if e.critic.verdict == "CORRECTED"),
            flags=sum(1 for e in self._entries if e.critic.verdict == "FLAGGED"),
        )

    def export(self) -> LedgerExport:
        return LedgerExport(
            protocol="map",
            version=f"{SPEC_VERSION}.0",
            entries=list(self._entries),
            stats=self.get_stats(),
        )

    def clear(self) -> None:
        self._entries = []
        self._store.clear()


__all__ = ["Ledger", "MapEvent", "MapEventHandler"]
