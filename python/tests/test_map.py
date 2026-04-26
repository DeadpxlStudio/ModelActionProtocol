"""Smoke tests for the Map orchestrator + reverser + critic surface."""

from __future__ import annotations

from typing import Any

import pytest

from map import (
    Action,
    CriticResult,
    EntryNotFound,
    Map,
    MapError,
    MemoryStore,
    NotReversible,
    rule_critic,
    verify_chain,
)


def _entry_dict(entry: Any) -> dict[str, Any]:
    return entry.model_dump(by_alias=True, exclude_none=True)


# ─── Map basic execution ────────────────────────────────────────────────────


def test_map_execute_records_entry_with_pass_critic_default() -> None:
    m = Map()
    entry = m.execute(Action(tool="ping", input={}, output="pong"))
    assert entry.critic.verdict == "PASS"
    assert entry.action.tool == "ping"
    assert m.get_stats().total == 1


def test_map_execute_with_rule_critic_corrects() -> None:
    def fail_on_negative(action: Action, sb: Any, sa: Any) -> CriticResult | None:
        if action.input.get("amount", 0) < 0:
            return CriticResult(
                verdict="CORRECTED",
                reason="negative amount; flipping sign",
                correction={"tool": action.tool, "input": {"amount": abs(action.input["amount"])}},  # type: ignore[arg-type]
            )
        return None

    m = Map()
    m.set_critic(rule_critic([fail_on_negative]))
    entry = m.execute(Action(tool="charge", input={"amount": -50}, output={"ok": True}))
    assert entry.critic.verdict == "CORRECTED"
    assert entry.critic.correction is not None
    assert entry.critic.correction.input == {"amount": 50}


def test_map_chain_remains_verifiable_under_orchestrator() -> None:
    m = Map()
    for i in range(3):
        m.execute(Action(tool="step", input={"i": i}, output={"i": i}))
    chain = [_entry_dict(e) for e in m.get_entries()]
    assert verify_chain(chain) == {"valid": True}


# ─── Reverser registration + rollback ──────────────────────────────────────


def test_reversible_decorator_registers_and_invokes_on_rollback() -> None:
    m = Map()
    reversed_calls: list[tuple[str, Any]] = []

    def cancel_order(action: Action, output: Any) -> Any:
        reversed_calls.append((action.tool, output))
        return {"cancelled": output.get("orderId")}

    @m.reversible(reverser=cancel_order)
    def place_order(item_id: str, quantity: int) -> dict[str, Any]:
        return {"orderId": f"O-{item_id}-{quantity}"}

    output = place_order(item_id="abc", quantity=2)
    entry = m.execute(
        Action(
            tool="place_order",
            input={"item_id": "abc", "quantity": 2},
            output=output,
        )
    )

    m.rollback_to(entry.id)
    assert reversed_calls == [("place_order", output)]


def test_rollback_to_unknown_id_raises_entry_not_found() -> None:
    m = Map()
    with pytest.raises(EntryNotFound):
        m.rollback_to("does-not-exist")


def test_rollback_continues_when_reverser_missing() -> None:
    m = Map()
    entry = m.execute(Action(tool="some_unregistered_tool", input={}, output=None))
    # No reverser registered — rollback should still mark the entry rolled-back.
    m.rollback_to(entry.id)
    after = m.get_entry(entry.id)
    assert after is not None
    assert after.status == "ROLLED_BACK"


def test_registry_execute_raises_not_reversible_directly() -> None:
    m = Map()
    with pytest.raises(NotReversible):
        m.reversers.execute(Action(tool="never_registered", input={}, output=None), None)


def test_map_error_is_root_for_all_subclasses() -> None:
    assert issubclass(EntryNotFound, MapError)
    assert issubclass(NotReversible, MapError)


# ─── Anthropic integration smoke ───────────────────────────────────────────


def test_wrap_tool_call_records_ledger_entry() -> None:
    """`integrations.anthropic.wrap_tool_call` runs the tool and ledgers the action."""
    from map.integrations.anthropic import wrap_tool_call

    m = Map()

    def get_weather(city: str) -> dict[str, Any]:
        return {"city": city, "temp_f": 72}

    block = {"type": "tool_use", "id": "toolu_1", "name": "get_weather", "input": {"city": "SF"}}
    result = wrap_tool_call(m, block, {"get_weather": get_weather})

    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "toolu_1"
    assert "is_error" not in result

    entries = m.get_entries()
    assert len(entries) == 1
    assert entries[0].action.tool == "get_weather"
    assert entries[0].action.output == {"city": "SF", "temp_f": 72}


def test_wrap_tool_call_handles_missing_tool() -> None:
    from map.integrations.anthropic import wrap_tool_call

    m = Map()
    block = {"type": "tool_use", "id": "toolu_2", "name": "no_such_tool", "input": {}}
    result = wrap_tool_call(m, block, {})

    assert result["is_error"] is True
    assert "unknown tool" in result["content"]
    # No ledger entry written for an unknown tool.
    assert len(m.get_entries()) == 0


def test_wrap_tool_call_handles_tool_exception() -> None:
    from map.integrations.anthropic import wrap_tool_call

    m = Map()

    def boom(**_kw: Any) -> Any:
        raise RuntimeError("kapow")

    block = {"type": "tool_use", "id": "toolu_3", "name": "boom", "input": {}}
    result = wrap_tool_call(m, block, {"boom": boom})

    assert result["is_error"] is True
    assert "kapow" in result["content"]
    # Ledger entry not written when the tool raised — the action didn't complete.
    assert len(m.get_entries()) == 0
