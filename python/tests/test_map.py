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


# ─── Verification items from the v0.1.0-rc1 review ─────────────────────────


def test_rollback_stop_on_first_failure_leaves_ledger_untouched() -> None:
    """Verification item #1 — rollback semantics under partial failure.

    A failing reverser must propagate as ReversalFailed and the ledger
    MUST remain untouched (no entries marked ROLLED_BACK, no rollback
    record appended). This is the all-or-nothing guarantee at the ledger
    layer, locked in v0.1.
    """
    from map import ReversalFailed

    m = Map()

    def good_reverser(action: Action, output: Any) -> Any:
        return None

    def boom_reverser(action: Action, output: Any) -> Any:
        raise RuntimeError("reverser exploded")

    @m.reversible(reverser=good_reverser)
    def first_action(x: int) -> dict[str, Any]:
        return {"ok": True}

    @m.reversible(reverser=boom_reverser)
    def second_action(x: int) -> dict[str, Any]:
        return {"ok": True}

    e1 = m.execute(Action(tool="first_action", input={"x": 1}, output={"ok": True}))
    e2 = m.execute(Action(tool="second_action", input={"x": 2}, output={"ok": True}))

    # rollback_to(e1) reverses e2 first (newest), then e1.
    # e2's reverser raises → ledger is untouched, exception propagates.
    with pytest.raises(ReversalFailed):
        m.rollback_to(e1.id)

    # Ledger must be unchanged.
    assert m.get_entry(e1.id).status == "ACTIVE"
    assert m.get_entry(e2.id).status == "ACTIVE"
    # No ROLLBACK record was appended.
    assert all(e.action.tool != "ROLLBACK" for e in m.get_entries())


def test_rollback_runs_reversers_newest_first() -> None:
    """Saga compensation order — newest-first, oldest-last."""
    m = Map()
    invocation_order: list[str] = []

    def make_reverser(name: str):
        def _r(action: Action, output: Any) -> Any:
            invocation_order.append(name)
            return None

        return _r

    @m.reversible(reverser=make_reverser("first"))
    def first(x: int) -> dict[str, Any]:
        return {"ok": True}

    @m.reversible(reverser=make_reverser("second"))
    def second(x: int) -> dict[str, Any]:
        return {"ok": True}

    @m.reversible(reverser=make_reverser("third"))
    def third(x: int) -> dict[str, Any]:
        return {"ok": True}

    e1 = m.execute(Action(tool="first", input={"x": 1}, output={"ok": True}))
    m.execute(Action(tool="second", input={"x": 2}, output={"ok": True}))
    m.execute(Action(tool="third", input={"x": 3}, output={"ok": True}))

    m.rollback_to(e1.id)
    assert invocation_order == ["third", "second", "first"]


def test_decorator_stack_warns_on_overwrite(caplog: Any) -> None:
    """Verification item #2 — stacking decorators on one fn warns on overwrite.

    Both ``@m.reversible`` and ``@m.escalate`` register a reverser keyed by
    the function name. The second registration silently overwrote the first
    in pre-rc1; rc2 emits a WARNING under logger ``map.reversal``.
    """
    import logging

    m = Map()

    def reverser_one(action: Action, output: Any) -> Any:
        return None

    with caplog.at_level(logging.WARNING, logger="map.reversal"):
        @m.reversible(reverser=reverser_one)
        @m.escalate(approver="ceo@example.com")
        def my_action(x: int) -> dict[str, Any]:
            return {"ok": True}

    overwrite_warnings = [r for r in caplog.records if "reverser overwrite" in r.message]
    assert overwrite_warnings, "expected a 'reverser overwrite' warning when stacking decorators"


def test_tool_schema_shape_matches_anthropic_tool_definition() -> None:
    """Verification item #3 — `tool_schema` produces an Anthropic-compatible shape.

    Anthropic's `messages.create(tools=[...])` expects each tool to have
    `name`, `description`, and `input_schema` (with `type: "object"`).
    """
    m = Map()

    def reverser(action: Action, output: Any) -> Any:
        return None

    @m.reversible(reverser=reverser)
    def place_order(item_id: str, quantity: int = 1) -> dict[str, Any]:
        """Place a customer order for a product.

        item_id is the SKU; quantity defaults to 1.
        """
        return {"orderId": "O-1"}

    schema = place_order.tool_schema  # type: ignore[attr-defined]
    assert schema["name"] == "place_order"
    assert "Place a customer order" in schema["description"]
    assert schema["input_schema"]["type"] == "object"
    assert "item_id" in schema["input_schema"]["properties"]
    assert schema["input_schema"]["properties"]["item_id"] == {"type": "string"}
    # quantity has a default, so it is NOT required
    assert "item_id" in schema["input_schema"]["required"]
    assert "quantity" not in schema["input_schema"]["required"]


def test_learning_export_shape_documented() -> None:
    """Verification item #4 — fine-tuning export shape is the documented MAP-native shape."""
    from map import LearningEngine
    from map.core.action import LedgerEntry

    m = Map()
    entry = m.execute(
        Action(tool="x", input={}, output=None),
    )
    # Force an "approved" annotation so the entry shows up in export.
    m.ledger._entries[0] = entry.model_copy(
        update={
            "approval": "approved",
            "critic": entry.critic.model_copy(update={"verdict": "CORRECTED"}),
        }
    )

    engine = LearningEngine()
    exported = engine.export_fine_tuning_data(m.get_entries())
    assert len(exported) == 1
    item = exported[0]
    # Shape per docstring: {input: {action, stateBefore, stateAfter}, output: {...}, humanApproval}
    assert set(item.keys()) == {"input", "output", "humanApproval"}
    assert set(item["input"].keys()) == {"action", "stateBefore", "stateAfter"}
    assert "verdict" in item["output"]
    assert item["humanApproval"] == "approved"
