"""SDK integration test — MAP wraps an Anthropic tool-use loop.

The canonical scenario for the integration: a researcher's existing
Anthropic-driven agent loop, with MAP slipped in as the layer that
captures every tool call as a verifiable ledger entry.

This test uses a mocked client (no API calls). The live variant in
`test_sdk_integration_live.py` runs the same scenario against the real
API and is gated on `ANTHROPIC_API_KEY`.

The same flow powers `examples/fastapi_app/main.py` — same artifact, two
purposes (CI gate + marketing demo).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from map import (
    Action,
    Map,
    ReversalFailed,
    rule_critic,
)
from map.core.action import CriticResult
from map.integrations.anthropic import wrap_tool_call


# ─── Fixtures: a tiny mock of the Anthropic Messages response shape ────────


@dataclass
class _MockToolUseBlock:
    type: str
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class _MockTextBlock:
    type: str
    text: str


@dataclass
class _MockResponse:
    content: list[Any]


# ─── The tool the agent has access to ──────────────────────────────────────

# In a real app this would talk to a fulfillment API. For the test we keep
# track of placed orders in a module-level dict so the reverser can find
# the order to cancel.

_PLACED_ORDERS: dict[str, dict[str, Any]] = {}


def place_order(item_id: str, quantity: int) -> dict[str, Any]:
    """Place a customer order. Returns the order record."""
    order_id = f"O-{item_id}-{quantity}-{len(_PLACED_ORDERS)}"
    record = {"orderId": order_id, "item_id": item_id, "quantity": quantity, "status": "open"}
    _PLACED_ORDERS[order_id] = record
    return record


def cancel_order(action: Action, output: Any) -> dict[str, Any]:
    """Reverser for `place_order` — flip the status to cancelled."""
    order_id = output["orderId"]
    if order_id not in _PLACED_ORDERS:
        raise RuntimeError(f"no such order {order_id}")
    _PLACED_ORDERS[order_id]["status"] = "cancelled"
    return {"orderId": order_id, "cancelled": True}


@pytest.fixture(autouse=True)
def _reset_orders() -> Any:
    _PLACED_ORDERS.clear()
    yield
    _PLACED_ORDERS.clear()


# ─── The integration scenario ───────────────────────────────────────────────


def _build_agent() -> tuple[Map, Any]:
    """Build the MAP instance and register the order-placing tool.

    Returns (map_instance, place_order_callable).
    """
    m = Map()

    # Register a deterministic critic so the test doesn't need an LLM.
    def disallow_huge_orders(
        action: Action, sb: Any, sa: Any
    ) -> CriticResult | None:
        if action.tool == "place_order" and action.input.get("quantity", 0) > 100:
            return CriticResult(
                verdict="FLAGGED",
                reason="quantity over 100 requires human approval",
            )
        return None

    m.set_critic(rule_critic([disallow_huge_orders]))

    # Decorate the tool. Note: the wrapped function's __name__ (preserved
    # by functools.wraps) is what becomes the registry key — here, "place_order".
    decorated = m.reversible(reverser=cancel_order)(place_order)

    return m, decorated


def test_full_tool_use_loop_records_ledger_entry() -> None:
    """A successful tool call produces a verifiable ledger entry."""
    m, place_order = _build_agent()

    # Mock Anthropic response — model decided to call place_order.
    response = _MockResponse(
        content=[
            _MockTextBlock(type="text", text="I'll place that order for you."),
            _MockToolUseBlock(
                type="tool_use",
                id="toolu_01",
                name="place_order",
                input={"item_id": "SKU-42", "quantity": 2},
            ),
        ]
    )

    registry = {"place_order": place_order}
    results = []
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            results.append(wrap_tool_call(m, block, registry))

    # The agent loop produced one tool_result block per tool_use block.
    assert len(results) == 1
    result = results[0]
    assert result["type"] == "tool_result"
    assert result["tool_use_id"] == "toolu_01"
    assert "is_error" not in result

    # The ledger captured the action.
    entries = m.get_entries()
    assert len(entries) == 1
    entry = entries[0]
    assert entry.action.tool == "place_order"
    assert entry.action.input == {"item_id": "SKU-42", "quantity": 2}
    assert entry.action.output["status"] == "open"
    assert entry.critic.verdict == "PASS"

    # The order was actually placed in the world.
    assert any(o["status"] == "open" for o in _PLACED_ORDERS.values())


def test_flagged_action_is_recorded_with_flagged_verdict() -> None:
    """When the critic flags an action, it still appears in the ledger.

    The decision to halt or continue execution belongs to the agent
    loop, not MAP. MAP records the verdict and lets the loop decide.
    """
    m, place_order = _build_agent()

    response = _MockResponse(
        content=[
            _MockToolUseBlock(
                type="tool_use",
                id="toolu_02",
                name="place_order",
                input={"item_id": "SKU-99", "quantity": 1000},  # over threshold
            )
        ]
    )

    registry = {"place_order": place_order}
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            wrap_tool_call(m, block, registry)

    entries = m.get_entries()
    assert len(entries) == 1
    assert entries[0].critic.verdict == "FLAGGED"
    assert "quantity over 100" in entries[0].critic.reason


def test_rollback_invokes_reverser_and_undoes_world_state() -> None:
    """Rollback walks reversers newest-first; world state changes."""
    m, place_order = _build_agent()

    # Two successful placements.
    blocks = [
        _MockToolUseBlock(
            type="tool_use",
            id="toolu_a",
            name="place_order",
            input={"item_id": "SKU-A", "quantity": 1},
        ),
        _MockToolUseBlock(
            type="tool_use",
            id="toolu_b",
            name="place_order",
            input={"item_id": "SKU-B", "quantity": 1},
        ),
    ]
    registry = {"place_order": place_order}
    for block in blocks:
        wrap_tool_call(m, block, registry)

    assert all(o["status"] == "open" for o in _PLACED_ORDERS.values())
    first_entry = m.get_entries()[0]

    # Rollback to the first entry → both should be cancelled in the world.
    m.rollback_to(first_entry.id)

    assert all(o["status"] == "cancelled" for o in _PLACED_ORDERS.values())

    # Ledger reflects the rollback: both entries ROLLED_BACK + a ROLLBACK record.
    entries = m.get_entries()
    rolled_back = [e for e in entries if e.status == "ROLLED_BACK"]
    assert len(rolled_back) == 2
    assert any(e.action.tool == "ROLLBACK" for e in entries)


def test_rollback_failure_leaves_ledger_untouched() -> None:
    """rc2 semantics: a failing reverser propagates and the ledger is unchanged."""
    m = Map()

    # Reverser that raises on the second-most-recent entry.
    def failing_reverser(action: Action, output: Any) -> Any:
        raise RuntimeError("simulated downstream API failure")

    @m.reversible(reverser=failing_reverser)
    def fragile_action(x: int) -> dict[str, Any]:
        return {"ok": True}

    e1 = m.execute(Action(tool="fragile_action", input={"x": 1}, output={"ok": True}))
    e2 = m.execute(Action(tool="fragile_action", input={"x": 2}, output={"ok": True}))

    pre_rollback_entries = list(m.get_entries())
    with pytest.raises(ReversalFailed):
        m.rollback_to(e1.id)

    # Ledger UNTOUCHED — no new ROLLBACK record, no status flips.
    post_rollback_entries = list(m.get_entries())
    assert len(post_rollback_entries) == len(pre_rollback_entries)
    assert all(e.status == "ACTIVE" for e in post_rollback_entries)


def test_unknown_tool_returns_error_block_no_ledger_entry() -> None:
    """When the model hallucinates a tool name, integration returns an error block."""
    m, _ = _build_agent()
    block = _MockToolUseBlock(
        type="tool_use",
        id="toolu_x",
        name="hallucinated_tool",
        input={},
    )
    result = wrap_tool_call(m, block, {"place_order": place_order})
    assert result["is_error"] is True
    assert "unknown tool" in result["content"]
    assert len(m.get_entries()) == 0


def test_chain_remains_verifiable_after_full_session() -> None:
    """Across a multi-tool-call session, the ledger still verifies as a clean chain."""
    from map import verify_chain

    m, place_order = _build_agent()

    for i in range(5):
        block = _MockToolUseBlock(
            type="tool_use",
            id=f"toolu_{i}",
            name="place_order",
            input={"item_id": f"SKU-{i}", "quantity": 1},
        )
        wrap_tool_call(m, block, {"place_order": place_order})

    chain = [e.model_dump(by_alias=True, exclude_none=True) for e in m.get_entries()]
    assert verify_chain(chain) == {"valid": True}
