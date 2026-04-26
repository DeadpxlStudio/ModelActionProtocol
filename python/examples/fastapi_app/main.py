"""FastAPI demo — MAP wrapping a tool-execution service.

Same scenario as ``tests/test_sdk_integration.py`` lifted into an HTTP
service. A real app would put auth, rate limiting, and validation in
front of these endpoints; the demo focuses on showing what MAP looks
like in a backend context.

Run::

    pip install "model-action-protocol[fastapi]"
    uvicorn main:app --reload

Endpoints::

    POST /execute            run a tool and record the call as a ledger entry
    POST /rollback/{id}      walk reversers newest-first; raise on first failure
    GET  /ledger             full audit export (MAP wire format)
    GET  /learning/patterns  observed correction patterns

Why ``asyncio.to_thread``? MAP is sync at v0.1 (DESIGN.md §2). FastAPI
handlers are async. Calling sync MAP code directly from an async handler
blocks the event loop — fine for a demo, real cost in production. The
``to_thread`` wrapper offloads each MAP call to a worker thread so the
event loop stays free. v0.2 will ship ``AsyncMap`` as a sibling class
and these wrappers go away.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from map import (
    Action,
    EntryNotFound,
    LearningEngine,
    Map,
    NotReversible,
    ReversalFailed,
    rule_critic,
)
from map.core.action import CriticResult
from map.stores.sqlite import SQLiteLedgerStore

DB_PATH = Path(__file__).parent / "ledger.db"


# ─── Tool + reverser ────────────────────────────────────────────────────────

# In a real app this would call a fulfillment service. The demo keeps state
# in an in-memory dict so curl smoke tests work end-to-end without infra.
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


# ─── MAP setup (process-singleton, dependency-injected into handlers) ──────


def _build_map() -> Map:
    store = SQLiteLedgerStore(DB_PATH)
    m = Map(store=store)

    # Critic example: flag wildly large orders. In production you'd compose
    # an LLM critic via map.llm_critic for non-deterministic checks.
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

    decorated = m.reversible(reverser=cancel_order)(place_order)
    m._tool_registry = {"place_order": decorated}  # demo-only convenience
    return m


_app_map: Map | None = None


def get_map() -> Map:
    """FastAPI dependency. Lazy-initialized; one Map per process."""
    global _app_map
    if _app_map is None:
        _app_map = _build_map()
    return _app_map


# ─── HTTP layer ─────────────────────────────────────────────────────────────


class ExecuteRequest(BaseModel):
    tool: str
    input: dict[str, Any]


class ExecuteResponse(BaseModel):
    entry_id: str
    sequence: int
    verdict: str
    output: Any


app = FastAPI(
    title="MAP demo",
    description="Tool execution under MAP — every call is a verifiable ledger entry.",
    version="0.1.0",
)


@app.post("/execute", response_model=ExecuteResponse)
async def execute(req: ExecuteRequest, m: Map = Depends(get_map)) -> ExecuteResponse:
    """Run a tool via MAP. Records a ledger entry. Returns the verdict + output."""
    registry = m._tool_registry  # type: ignore[attr-defined]
    tool_fn = registry.get(req.tool)
    if tool_fn is None:
        raise HTTPException(status_code=404, detail=f"unknown tool {req.tool!r}")

    def _run_in_thread() -> tuple[Any, Any]:
        # MAP is sync at v0.1 (DESIGN.md §2). v0.2 will provide AsyncMap and
        # this thread offload goes away.
        try:
            output = tool_fn(**req.input)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"tool failed: {e}") from e
        action = Action(tool=req.tool, input=req.input, output=output)
        entry = m.execute(action)
        return entry, output

    entry, output = await asyncio.to_thread(_run_in_thread)
    return ExecuteResponse(
        entry_id=entry.id,
        sequence=entry.sequence,
        verdict=entry.critic.verdict,
        output=output,
    )


@app.post("/rollback/{entry_id}")
async def rollback(entry_id: str, m: Map = Depends(get_map)) -> dict[str, Any]:
    """Roll back to ``entry_id``. Reversers run newest-first; stop-on-first-failure.

    On reverser failure: ledger is untouched, 502 returned with the reason.
    Already-completed reverser side effects in the world are NOT undone — see
    DESIGN.md §2 / SPEC.md §10.
    """
    def _run() -> dict[str, Any]:
        # Sync MAP call → offload from the event loop.
        return m.rollback_to(entry_id)

    try:
        result = await asyncio.to_thread(_run)
    except EntryNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except (NotReversible, ReversalFailed) as e:
        raise HTTPException(
            status_code=502,
            detail={
                "error": type(e).__name__,
                "message": str(e),
                "note": "ledger untouched; reverser side effects already in the world are not undone",
            },
        ) from e

    return {
        "entries_reverted": result["entriesReverted"],
        "ledger": "rolled back",
    }


@app.get("/ledger")
async def ledger(m: Map = Depends(get_map)) -> dict[str, Any]:
    """Full audit export per SPEC.md §8."""

    def _run() -> Any:
        return m.export().model_dump(by_alias=True, exclude_none=True)

    return await asyncio.to_thread(_run)


@app.get("/learning/patterns")
async def learning_patterns(m: Map = Depends(get_map)) -> dict[str, Any]:
    """Pattern fingerprints from the ledger (SPEC.md §6.3)."""

    def _run() -> dict[str, Any]:
        engine = LearningEngine()
        patterns = engine.analyze_patterns(m.get_entries())
        return {
            "patterns": [
                p.model_dump(by_alias=True, exclude_none=True) for p in patterns
            ],
            "count": len(patterns),
        }

    return await asyncio.to_thread(_run)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "MAP demo",
        "spec": "https://github.com/DeadpxlStudio/ModelActionProtocol/blob/main/spec/SPEC.md",
        "endpoints": "POST /execute, POST /rollback/{id}, GET /ledger, GET /learning/patterns",
    }
