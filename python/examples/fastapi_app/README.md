# MAP FastAPI demo

A minimal HTTP service that wraps a tool-execution endpoint with MAP. Every tool call is a verifiable ledger entry; rollback walks reversers newest-first.

This is the same scenario that `tests/test_sdk_integration.py` exercises, lifted into a FastAPI app. Read the test for the canonical narrative, this README for the HTTP surface.

## Run

```bash
pip install "map-protocol[fastapi]"
cd python/examples/fastapi_app
uvicorn main:app --reload
```

## API

### `POST /execute`

Run a tool. Records a ledger entry and returns the verdict + output.

```bash
curl -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -d '{"tool": "place_order", "input": {"item_id": "SKU-42", "quantity": 2}}'
```

Response:

```json
{
  "entry_id": "12345678-1234-4abc-8def-...",
  "sequence": 0,
  "verdict": "PASS",
  "output": {"orderId": "O-SKU-42-2-0", "item_id": "SKU-42", "quantity": 2, "status": "open"}
}
```

A FLAGGED action (the demo flags any order with `quantity > 100`) still records but the verdict tells you about it:

```bash
curl -X POST http://localhost:8000/execute \
  -d '{"tool": "place_order", "input": {"item_id": "SKU-99", "quantity": 1000}}'
# verdict: "FLAGGED"
```

The decision to halt or continue execution belongs to the agent loop, not MAP.

### `POST /rollback/{entry_id}`

Roll back to an entry. Reversers run newest-first. If any reverser fails, the ledger is untouched and a 502 is returned.

```bash
curl -X POST http://localhost:8000/rollback/12345678-1234-4abc-8def-...
```

Response on success:

```json
{"entries_reverted": 1, "ledger": "rolled back"}
```

Response on reverser failure (502):

```json
{
  "detail": {
    "error": "ReversalFailed",
    "message": "reverser for tool 'place_order' raised: ...",
    "note": "ledger untouched; reverser side effects already in the world are not undone"
  }
}
```

### `GET /ledger`

The full audit export — MAP wire format per [`SPEC.md` §8](../../../spec/SPEC.md).

```bash
curl http://localhost:8000/ledger | jq
```

### `GET /learning/patterns`

Pattern fingerprints from the ledger (SPEC.md §6.3) — what corrections have been observed and how often.

```bash
curl http://localhost:8000/learning/patterns
```

## Implementation notes

**`asyncio.to_thread` wrapping every MAP call.** MAP is sync at v0.1 ([DESIGN.md §2](../../DESIGN.md)). FastAPI handlers are async. Calling sync MAP code directly from an async handler blocks the event loop. The wrapper offloads to a worker thread; the event loop stays free.

v0.2 will ship `AsyncMap` as a sibling class. When you upgrade, the wrappers go away — `result = await async_map.execute(action)` replaces `await asyncio.to_thread(map.execute, action)`.

**SQLite store, file-backed.** `ledger.db` is created next to `main.py`. Persists across restarts. For multi-process deployments switch to `PostgresLedgerStore`.

**`_tool_registry` on the Map instance.** Demo-only convenience — production code would manage tool registration via dependency injection or a service registry.

## End-to-end smoke test

```bash
# place an order
RESP=$(curl -s -X POST http://localhost:8000/execute \
  -d '{"tool": "place_order", "input": {"item_id": "SKU-A", "quantity": 1}}')
ENTRY_ID=$(echo $RESP | jq -r .entry_id)
echo "placed; entry $ENTRY_ID"

# verify the ledger has it
curl -s http://localhost:8000/ledger | jq '.stats'

# roll it back
curl -s -X POST "http://localhost:8000/rollback/$ENTRY_ID"

# verify the ledger reflects the rollback
curl -s http://localhost:8000/ledger | jq '.stats'
```
