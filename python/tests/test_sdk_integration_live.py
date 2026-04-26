"""Live SDK integration test — MAP wraps a real Anthropic tool-use call.

Same scenario as ``test_sdk_integration.py`` but hits the real Anthropic
API. Catches mock-drift the unit test won't see: response shape changes
across SDK versions, tool-use response variations, etc.

Gated on ``ANTHROPIC_API_KEY``. Marked ``live_api`` so PR runs skip it;
nightly CI runs it via ``pytest -m live_api``.

Cost: one ``messages.create`` call per test execution, on the cheapest
model that supports tool use. Negligible.

If this test breaks before the mocked one does, the SDK changed shape
and the mocked test's fixtures need updating.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

# Module-level skip if the SDK isn't installed — keeps `pytest --collect-only`
# clean on environments without the [anthropic] extra.
anthropic = pytest.importorskip(
    "anthropic",
    reason="anthropic SDK not installed; install model-action-protocol[anthropic] to run",
)

from map import (  # noqa: E402
    Action,
    Map,
    rule_critic,
)
from map.core.action import CriticResult  # noqa: E402
from map.integrations.anthropic import wrap_tool_call  # noqa: E402

pytestmark = [
    pytest.mark.live_api,
    pytest.mark.skipif(
        "ANTHROPIC_API_KEY" not in os.environ,
        reason="ANTHROPIC_API_KEY not set",
    ),
]


# Module-level state shared with the reverser, mirroring the mocked test.
_PLACED_ORDERS: dict[str, dict[str, Any]] = {}


def place_order(item_id: str, quantity: int) -> dict[str, Any]:
    """Place a customer order. Returns the order record."""
    order_id = f"O-{item_id}-{quantity}-{len(_PLACED_ORDERS)}"
    record = {
        "orderId": order_id,
        "item_id": item_id,
        "quantity": quantity,
        "status": "open",
    }
    _PLACED_ORDERS[order_id] = record
    return record


def cancel_order(action: Action, output: Any) -> dict[str, Any]:
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


# ─── The live scenario ─────────────────────────────────────────────────────


def test_live_anthropic_tool_call_records_ledger_entry() -> None:
    """End-to-end: real Anthropic call → MAP-wrapped tool execution → ledger entry.

    Uses ``tool_choice`` to force a specific tool call, so the assertions
    don't depend on the model's free-form decision-making.
    """
    client = anthropic.Anthropic()  # picks up ANTHROPIC_API_KEY from env

    m = Map()
    decorated = m.reversible(reverser=cancel_order)(place_order)
    tool_def = decorated.tool_schema  # type: ignore[attr-defined]

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        tools=[tool_def],
        tool_choice={"type": "tool", "name": "place_order"},
        messages=[
            {
                "role": "user",
                "content": "Place an order for SKU-LIVE-1, quantity 3.",
            }
        ],
    )

    # Walk the response, MAP-wrapping each tool_use block.
    registry = {"place_order": decorated}
    tool_results = []
    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            tool_results.append(wrap_tool_call(m, block, registry))

    # Forced tool_choice → at least one tool_use block expected.
    assert len(tool_results) >= 1, "expected the model to call place_order"

    # Each tool_result block has the right shape.
    for r in tool_results:
        assert r["type"] == "tool_result"
        assert "tool_use_id" in r

    # Ledger captured each call.
    assert len(m.get_entries()) == len(tool_results)
    for entry in m.get_entries():
        assert entry.action.tool == "place_order"
        assert entry.action.input.get("item_id")
        assert entry.action.input.get("quantity")

    # The world reflects the call.
    assert any(o["status"] == "open" for o in _PLACED_ORDERS.values())


def test_live_rollback_undoes_world_state() -> None:
    """Place an order via the live API, then roll it back via MAP."""
    client = anthropic.Anthropic()

    m = Map()
    decorated = m.reversible(reverser=cancel_order)(place_order)

    response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=512,
        tools=[decorated.tool_schema],  # type: ignore[attr-defined]
        tool_choice={"type": "tool", "name": "place_order"},
        messages=[
            {"role": "user", "content": "Place an order for SKU-ROLLBACK, quantity 1."}
        ],
    )

    for block in response.content:
        if getattr(block, "type", None) == "tool_use":
            wrap_tool_call(m, block, {"place_order": decorated})

    entries = m.get_entries()
    assert len(entries) >= 1
    assert all(o["status"] == "open" for o in _PLACED_ORDERS.values())

    # Roll back the first ledger entry. The reverser flips the world.
    m.rollback_to(entries[0].id)
    assert all(o["status"] == "cancelled" for o in _PLACED_ORDERS.values())
