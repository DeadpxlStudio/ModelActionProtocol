"""Tests for the Ledger class (sync per DESIGN.md §2).

Covers: append, hash chaining, tamper detection, rollback, status
transitions, export. Mirrors the TS-side coverage in
``Open Source/src/__tests__/map.test.ts`` and ``persistence.test.ts``.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from map import (
    Action,
    ActionRecord,
    CriticResult,
    EntryNotFound,
    Ledger,
    MemoryStore,
    compute_entry_hash,
    state_hash,
    to_jsonable,
    verify_chain,
)


def _entry_dict(entry: Any) -> dict[str, Any]:
    return entry.model_dump(by_alias=True, exclude_none=True)


# ─── Append + hash chain ────────────────────────────────────────────────────


def test_append_chains_hashes_correctly() -> None:
    ledger = Ledger()
    state: dict[str, Any] = {"counter": 0}

    for i in range(3):
        before = state
        state = {"counter": i + 1}
        ledger.append(
            Action(tool="increment", input={"by": 1}, output={"ok": True}),
            before,
            state,
            CriticResult(verdict="PASS", reason="ok"),
        )

    entries = [_entry_dict(e) for e in ledger.get_entries()]
    assert verify_chain(entries) == {"valid": True}


def test_genesis_parent_hash_is_zeros() -> None:
    ledger = Ledger()
    ledger.append(
        Action(tool="x", input={}, output=None),
        None,
        None,
        CriticResult(verdict="PASS", reason="ok"),
    )
    entries = ledger.get_entries()
    assert entries[0].parentHash == "0" * 64


def test_each_entry_hash_matches_recomputation() -> None:
    ledger = Ledger()
    for i in range(5):
        ledger.append(
            Action(tool="step", input={"i": i}, output={"i": i}),
            {"step": i},
            {"step": i + 1},
            CriticResult(verdict="PASS", reason="ok"),
        )

    for e in ledger.get_entries():
        expected = compute_entry_hash(
            sequence=e.sequence,
            action=to_jsonable(e.action),
            state_before=e.stateBefore,
            state_after=e.stateAfter,
            parent_hash=e.parentHash,
            critic=to_jsonable(e.critic),
        )
        assert e.hash == expected


def test_action_record_alias_still_imports() -> None:
    """ActionRecord is the spec name; Action is the Python class. Keep both."""
    a = ActionRecord(tool="x", input={}, output=None)
    assert isinstance(a, Action)


# ─── Rollback ───────────────────────────────────────────────────────────────


def test_rollback_marks_entries_and_appends_rollback_record() -> None:
    ledger = Ledger()

    ledger.append(
        Action(tool="add", input={"id": 1}, output={"ok": True}),
        {"items": []},
        {"items": [1]},
        CriticResult(verdict="PASS", reason="ok"),
    )
    second = ledger.append(
        Action(tool="add", input={"id": 2}, output={"ok": True}),
        {"items": [1]},
        {"items": [1, 2]},
        CriticResult(verdict="PASS", reason="ok"),
    )

    result = ledger.rollback_to(second.id)
    assert result["entriesReverted"] == 1

    entries = ledger.get_entries()
    assert len(entries) == 3
    assert entries[1].status == "ROLLED_BACK"
    assert entries[2].action.tool == "ROLLBACK"
    assert entries[2].status == "ACTIVE"

    chain = [_entry_dict(e) for e in entries]
    assert verify_chain(chain) == {"valid": True}


def test_rollback_to_unknown_id_raises_entry_not_found() -> None:
    ledger = Ledger()
    with pytest.raises(EntryNotFound):
        ledger.rollback_to("does-not-exist")


# ─── Status semantics ───────────────────────────────────────────────────────


def test_committed_entries_excludes_rolled_back() -> None:
    ledger = Ledger()

    e1 = ledger.append(
        Action(tool="x", input={}, output=None),
        None,
        {},
        CriticResult(verdict="PASS", reason="ok"),
    )
    ledger.rollback_to(e1.id)

    committed = ledger.get_committed_entries()
    # The rollback record itself is ACTIVE; the original is ROLLED_BACK.
    assert all(e.action.tool == "ROLLBACK" for e in committed)


# ─── Stats and export ──────────────────────────────────────────────────────


def test_stats_count_corrections_and_flags() -> None:
    ledger = Ledger()

    ledger.append(
        Action(tool="x", input={}, output=None),
        None,
        None,
        CriticResult(verdict="PASS", reason="ok"),
    )
    ledger.append(
        Action(tool="y", input={}, output=None),
        None,
        None,
        CriticResult(
            verdict="CORRECTED",
            reason="auto-fixed",
            correction={"tool": "y", "input": {"fixed": True}},  # type: ignore[arg-type]
        ),
    )
    ledger.append(
        Action(tool="z", input={}, output=None),
        None,
        None,
        CriticResult(verdict="FLAGGED", reason="dangerous"),
    )

    stats = ledger.get_stats()
    assert stats.total == 3
    assert stats.corrections == 1
    assert stats.flags == 1


def test_export_envelope_shape() -> None:
    ledger = Ledger()
    ledger.append(
        Action(tool="x", input={}, output=None),
        None,
        None,
        CriticResult(verdict="PASS", reason="ok"),
    )
    export = ledger.export()
    assert export.protocol == "map"
    assert export.version == "0.1.0"
    assert len(export.entries) == 1


# ─── Cross-language: Python writes, chain verifies ─────────────────────────


def test_python_written_ledger_verifies_via_chain_logic() -> None:
    ledger = Ledger(MemoryStore())
    for i in range(4):
        ledger.append(
            Action(
                tool="step",
                input={"i": i, "name": f"item-{i}"},
                output={"ok": True, "id": i},
            ),
            {"counter": i},
            {"counter": i + 1},
            CriticResult(verdict="PASS", reason="ok"),
        )

    chain = [_entry_dict(e) for e in ledger.get_entries()]
    assert verify_chain(chain) == {"valid": True}

    # Round-trip through JSON to simulate cross-language transport.
    json_str = json.dumps(chain)
    reloaded = json.loads(json_str)
    assert verify_chain(reloaded) == {"valid": True}


# ─── Tamper detection ───────────────────────────────────────────────────────


def test_modifying_an_entry_breaks_subsequent_chain() -> None:
    ledger = Ledger()
    for i in range(3):
        ledger.append(
            Action(tool="x", input={"i": i}, output=None),
            {"v": i},
            {"v": i + 1},
            CriticResult(verdict="PASS", reason="ok"),
        )

    chain = [_entry_dict(e) for e in ledger.get_entries()]
    chain[1] = {**chain[1], "action": {**chain[1]["action"], "tool": "tampered"}}
    result = verify_chain(chain)
    assert result["valid"] is False
    assert result["corruptedAt"] == 1


# ─── State hash determinism ─────────────────────────────────────────────────


def test_state_hash_independent_of_dict_key_order() -> None:
    ledger1 = Ledger()
    ledger2 = Ledger()

    state_a = {"x": 1, "y": 2}
    state_b = {"y": 2, "x": 1}

    e1 = ledger1.append(
        Action(tool="x", input={}, output=None),
        None,
        state_a,
        CriticResult(verdict="PASS", reason="ok"),
    )
    e2 = ledger2.append(
        Action(tool="x", input={}, output=None),
        None,
        state_b,
        CriticResult(verdict="PASS", reason="ok"),
    )

    assert e1.stateAfter == e2.stateAfter
    assert e1.hash == e2.hash
    assert state_hash(state_a) == state_hash(state_b)
