"""The ``Map`` orchestrator — top-level public class.

Owns:
- a ``Ledger`` (and via it, a ``LedgerStore``)
- a ``ReverserRegistry``
- an optional ``Critic``

Methods are sync per DESIGN.md §2. The orchestrator's only I/O hop is via
``self._ledger`` (which delegates to the store). Everything else is pure
CPU — the constraint that makes the v0.2 ``AsyncMap`` retrofit a sibling
class rather than a rewrite.

Surface (per DESIGN.md §13):

    m = Map(store=SQLiteStore("ledger.db"))

    @m.reversible(reverser=cancel_order)
    def place_order(item_id: str, quantity: int) -> dict: ...

    result = m.execute(action)
    m.rollback_to(entry.id)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, TypeVar

from .core.action import (
    Action,
    CriticResult,
    LedgerEntry,
    LedgerExport,
    LedgerStats,
)
from .core.critic import Critic
from .core.ledger import Ledger
from .core.reversal import Reverser, ReverserRegistry
from .exceptions import EntryNotFound
from .stores.memory import LedgerStore, MemoryStore
from .tools.decorators import (
    compensate as _compensate_decorator,
)
from .tools.decorators import (
    escalate as _escalate_decorator,
)
from .tools.decorators import (
    restore as _restore_decorator,
)
from .tools.decorators import (
    reversible as _reversible_decorator,
)

logger = logging.getLogger("map")

F = TypeVar("F", bound=Callable[..., Any])


class Map:
    """Top-level MAP orchestrator."""

    def __init__(
        self,
        *,
        store: LedgerStore | None = None,
        critic: Critic | None = None,
    ) -> None:
        self._ledger = Ledger(store=store if store is not None else MemoryStore())
        self._reversers = ReverserRegistry()
        self._critic: Critic | None = critic

    # ─── Critic configuration ──────────────────────────────────────────────

    def set_critic(self, critic: Critic | None) -> None:
        """Install or remove the critic. ``None`` means actions auto-PASS."""
        self._critic = critic

    @property
    def critic(self) -> Critic | None:
        return self._critic

    # ─── Reverser registration (decorator surface) ─────────────────────────

    def reversible(
        self,
        *,
        reverser: Reverser,
        description: str | None = None,
    ) -> Callable[[F], F]:
        """Mark a function reversible via a custom reverser callable."""
        return _reversible_decorator(
            self._reversers, reverser=reverser, description=description
        )

    def compensate(
        self,
        *,
        compensating_tool: str,
        input_mapping: dict[str, str] | None = None,
        description: str | None = None,
    ) -> Callable[[F], F]:
        return _compensate_decorator(
            self._reversers,
            compensating_tool=compensating_tool,
            input_mapping=input_mapping,
            description=description,
        )

    def restore(
        self,
        *,
        capture: Callable[..., Any],
        reverser: Reverser,
        capture_method: str | None = None,
        description: str | None = None,
    ) -> Callable[[F], F]:
        return _restore_decorator(
            self._reversers,
            capture=capture,
            reverser=reverser,
            capture_method=capture_method,
            description=description,
        )

    def escalate(
        self,
        *,
        approver: str,
        description: str | None = None,
    ) -> Callable[[F], F]:
        return _escalate_decorator(
            self._reversers, approver=approver, description=description
        )

    # ─── Imperative reverser registration (for non-decorator users) ────────

    def register_reverser(
        self,
        tool: str,
        reverser: Reverser,
    ) -> None:
        self._reversers.register(tool, reverser)

    # ─── Execution ─────────────────────────────────────────────────────────

    def execute(
        self,
        action: Action,
        *,
        state_before: Any = None,
        state_after: Any = None,
    ) -> LedgerEntry:
        """Run the critic on ``action`` and record the result in the ledger.

        ``state_before`` / ``state_after`` are recorded in the entry's
        snapshot fields. When omitted (the common SDK-integration case
        where MAP only sees tool calls, not application state), they
        default to ``None`` and the state hashes pin the genesis-of-state
        SHA-256.
        """
        critic_result = self._invoke_critic(action, state_before, state_after)
        return self._ledger.append(action, state_before, state_after, critic_result)

    def _record_action(
        self,
        action: Action,
        output: Any,
        state_before: Any = None,
        state_after: Any = None,
    ) -> LedgerEntry:
        """Internal helper used by ``integrations.anthropic.wrap_tool_call``.

        Treats the tool's actual ``output`` as the recorded action output.
        """
        # Refresh action.output in case the caller passed an empty placeholder.
        action_with_output = action.model_copy(update={"output": output})
        return self.execute(
            action_with_output,
            state_before=state_before,
            state_after=state_after,
        )

    def _invoke_critic(
        self,
        action: Action,
        state_before: Any,
        state_after: Any,
    ) -> CriticResult:
        if self._critic is None:
            return CriticResult(verdict="PASS", reason="no critic configured")
        try:
            return self._critic(action, state_before, state_after)
        except Exception as e:
            logger.warning("critic raised; failing closed to FLAGGED: %s", e)
            return CriticResult(
                verdict="FLAGGED",
                reason=f"critic raised (defaulting to FLAGGED): {e}",
            )

    # ─── Rollback ──────────────────────────────────────────────────────────

    def rollback_to(self, entry_id: str) -> dict[str, Any]:
        """Reverse all entries from ``entry_id`` onward and mark them ROLLED_BACK.

        **Semantics (v0.1, locked):**

        - Reversers run in **reverse-sequence order** — newest entry first,
          oldest last — matching saga compensation order.
        - Entries with no registered reverser are skipped silently (no
          reversal needed; common for read-only or non-side-effecting tools).
        - **Stop-on-first-failure for ledger state.** If any reverser raises
          (``NotReversible`` / ``ReversalFailed`` / any exception), this
          method propagates the exception and the ledger is **NOT** updated
          — no entries are marked ROLLED_BACK, no rollback record is
          appended. The ledger reflects only complete rollbacks.
        - **World-side effects from already-completed reversers persist.**
          MAP cannot un-cancel an order, un-refund a charge, or un-send an
          email. Callers receiving an exception MUST inspect the error,
          decide what to do about partially-reversed external state, and
          either re-attempt the rollback (the already-reversed entries will
          have been marked when the next attempt succeeds) or coordinate
          manual reconciliation.

        Only when every reverser succeeds does the ledger atomically mark
        the affected entries ROLLED_BACK and append a ROLLBACK provenance
        entry. This is "all-or-nothing at the ledger layer" — the strongest
        guarantee MAP can offer without a 2PC protocol.

        Returns:
            ``{"state": <restored snapshot>, "entriesReverted": <int>}``
            on full success.

        Raises:
            EntryNotFound: ``entry_id`` is not in the ledger.
            NotReversible: an affected entry has no registered reverser
                AND the runtime requires one (currently never — missing
                reversers are skipped silently in v0.1).
            ReversalFailed: a registered reverser raised. The exception
                wraps the underlying error; the failed entry's id and tool
                are in the message.
        """
        target = self._ledger.get_entry(entry_id)
        if target is None:
            raise EntryNotFound(f"no ledger entry with id {entry_id}")

        # Reverse-sequence order: newest first.
        affected = sorted(
            [
                e
                for e in self._ledger.get_entries()
                if e.sequence >= target.sequence and e.status == "ACTIVE"
            ],
            key=lambda e: e.sequence,
            reverse=True,
        )

        # Run all reversers first. Any failure short-circuits — the ledger
        # is left untouched.
        for e in affected:
            reverser = self._reversers.get_reverser(e.action.tool)
            if reverser is None:
                logger.debug(
                    "no reverser for tool %s on entry %s; skipping reverse-call",
                    e.action.tool,
                    e.id,
                )
                continue
            self._reversers.execute(e.action, e.action.output)

        # All reversers succeeded → update ledger state atomically.
        return self._ledger.rollback_to(entry_id)

    # ─── Read accessors ────────────────────────────────────────────────────

    def get_entries(self) -> list[LedgerEntry]:
        return self._ledger.get_entries()

    def get_entry(self, entry_id: str) -> LedgerEntry | None:
        return self._ledger.get_entry(entry_id)

    def get_stats(self) -> LedgerStats:
        return self._ledger.get_stats()

    def export(self) -> LedgerExport:
        return self._ledger.export()

    @property
    def ledger(self) -> Ledger:
        return self._ledger

    @property
    def reversers(self) -> ReverserRegistry:
        return self._reversers


__all__ = ["Map"]
