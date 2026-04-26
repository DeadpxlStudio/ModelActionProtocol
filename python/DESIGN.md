# MAP Python — Design Choices (v0.1, locked)

**Status:** Locked. Decisions made; deviations during implementation get back-pressure against this doc.

**Scope:** Pre-implementation design decisions for the MAP Python reference implementation. The MAP spec itself (data model, canonicalization, hashes) is authoritative — these are *implementation idiom* choices that the spec doesn't constrain.

**Audience:** Python AI/ML researchers using MAP from Jupyter notebooks, scripts, and FastAPI services. Compose-with: `anthropic`, `openai`, `litellm`, LangChain/LangGraph, DSPy.

---

## §1 — Data modeling library

**Decision: Pydantic v2.** Pin `pydantic>=2.5,<3`. No v1 support.

**Why:** Anthropic SDK responses, FastAPI, Instructor, Pydantic AI, LangChain — all Pydantic. Researchers reach for it without thinking. Dataclasses would force the FastAPI demo to maintain parallel Pydantic shadow models and forfeits free JSON schema export. Performance is no longer a real concern for MAP's volume.

---

## §2 — Sync vs async (locked)

**Decision: Sync all the way down at v0.1.** Async deferred to v0.2.

- **Public API:** sync at v0.1.
- **Internal I/O:** sync all the way down. No event loops, no thread pools, no `asyncio.run()` anywhere in the library.
- **Store Protocol:** sync-only at v0.1; async retrofit in v0.2 ships as a sibling `AsyncLedgerStore` Protocol and `AsyncMap` class — not a replacement.
- **Postgres driver:** `psycopg[binary]>=3` in sync mode (sync and async share the same library).
- **FastAPI demo:** `asyncio.to_thread()` at call sites, explicitly commented.
- **Constraint enforced for retrofit:** I/O lives only in store classes. Canonicalization, hashing, critic, and reversal logic are pure CPU.

That last constraint — "I/O lives only in store classes" — is the one that costs nothing now and saves the v0.2 async work from being a rewrite.

```python
# v0.1
class Map:
    def execute(self, action: Action) -> ExecutionResult: ...

# v0.2 — added later, sibling class, not replacement
class AsyncMap:
    async def execute(self, action: Action) -> ExecutionResult: ...
```

**Why:** Notebooks (the primary research surface) default to sync. Top-level await works but isn't where researchers reach. Async-only forces every notebook user into `asyncio.run()` ceremony. Both-at-once doubles the test surface before you know which async patterns researchers actually want (asyncio vs trio vs anyio). Ship sync, listen, add async in v0.2 with the right primitives.

```python
# FastAPI demo
@app.post("/execute")
async def execute_endpoint(req: ExecuteRequest):
    # MAP is sync at v0.1. Wrap in to_thread so we don't block the event loop.
    # v0.2 will provide AsyncMap; this wrapper goes away.
    result = await asyncio.to_thread(map_instance.execute, req.action)
    return result
```

---

## §3 — Interface declaration

**Decision: `typing.Protocol` with `@runtime_checkable`.** No ABC base classes for the public interfaces.

**Why:** Structural typing is the modern Python idiom and doesn't force inheritance. `@runtime_checkable` gives `isinstance()` checks for users who want them. ABC's value (runtime "you forgot to implement X" enforcement) is mostly subsumed by `mypy --strict` in CI. If a user wants a base class with shared helpers, MAP can ship `BaseLedgerStore` separately that *implements* the Protocol — clean separation.

---

## §4 — Error hierarchy

**Decision: Layered hierarchy, single `MapError` root, no stdlib multi-inheritance.**

```
MapError
├── ValidationError       (input shape wrong, schema violation)
├── LedgerError
│   ├── LedgerCorruption  (hash chain broken)
│   ├── EntryNotFound
│   └── StoreError        (DB connection, IO)
├── ReversalError
│   ├── NotReversible     (no reverser registered)
│   └── ReversalFailed    (executed but failed)
├── CriticError
└── ConformanceError      (cross-language conformance check failed)
```

**Why:** Single root makes "catch everything from MAP" trivial. Sub-classes let researchers handle specific failures (e.g., catch `LedgerCorruption` to trigger a rebuild). Multi-inheriting from `ValueError` etc. is clever and surprising — surprises in error handling are bugs.

---

## §5 — Package layout

**Decision:**

```
map/
├── __init__.py           # Public API re-exports only
├── _version.py           # Single source of version truth
├── core/
│   ├── action.py
│   ├── ledger.py
│   ├── snapshot.py
│   ├── reversal.py
│   ├── critic.py
│   └── canonical.py      # JCS canonicalization, hashing
├── stores/
│   ├── memory.py
│   ├── sqlite.py
│   └── postgres.py
├── learning/
│   └── engine.py
├── tools/
│   └── decorators.py
├── integrations/
│   └── anthropic.py      # SDK wrapper helpers
├── exceptions.py
└── py.typed              # PEP 561 marker
```

Public surface at `map`:
```python
from map import Map, Action, Ledger, LedgerEntry, Reversal, MapError
from map.stores import MemoryStore, SQLiteStore, PostgresStore
```

**Why:** Flat-ish, predictable, separates pluggable backends (`stores/`) from core primitives (`core/`). `_version.py` keeps the version a single edit. `py.typed` is non-negotiable — without it, downstream type checkers ignore MAP's types even though we ship them. Underscore prefix on internals signals "don't depend on this."

---

## §6 — Testing

**Decision: pytest + hypothesis + markers.**

- pytest, not unittest
- Markers: `@pytest.mark.conformance`, `@pytest.mark.integration`, `@pytest.mark.perf`, `@pytest.mark.postgres`, `@pytest.mark.live_api`
- Phase 1 filter: `pytest -m "not conformance and not integration and not perf and not postgres and not live_api"`
- `DB_HOST` gates `postgres`; `ANTHROPIC_API_KEY` gates `live_api`
- Conformance fixtures loaded via `session`-scoped fixture
- `hypothesis` for canonicalization property tests ("any valid action canonicalizes idempotently")

**Why:** Markers beat `-k` string matching for clarity and CI config. hypothesis catches canonicalization edge cases enumeration won't (the unicode/number/key-ordering bugs that bite cross-language hash protocols on day one).

---

## §7 — Logging

**Decision: stdlib `logging`, namespaced under `map`, `NullHandler` attached by default.**

Logger names: `map`, `map.ledger`, `map.critic`, `map.stores.postgres`, `map.integrations.anthropic`. README documents the names and recommended levels.

**Why:** Researchers integrate MAP into existing pipelines with their own logging configured. structlog/loguru would override that. MAP's job is to compose, not dictate. `NullHandler` prevents the "no handlers" warning without forcing config.

---

## §8 — Type checking

**Decision: `mypy --strict` is the floor, run in CI. Pyright runs in CI as well if the budget allows; otherwise documented as supported.**

**Why:** Strict mypy catches the bugs that matter for a library shipping types. Pyright is faster and catches some things mypy doesn't (and vice versa). For a library the audience is going to pyright-check (VSCode default), being clean in both is the right bar.

---

## §9 — Python version support

**Decision: 3.10–3.14.** `requires-python = ">=3.10,<3.15"`.

**Why:** 3.10 gives `match` statements (clean reversal dispatch) and `X | Y` type syntax. 3.9 is at end-of-life for new libraries. 3.14 shipped while v0.1 was being built; the upper bound was relaxed from `<3.14` to `<3.15` during refactor and 3.14 verified working on the dev system.

---

## §10 — Dependencies

**Decision: Pydantic v2 only at core. Everything else is an extra.**

**Required:**
- `pydantic>=2.5,<3`
- JCS canonicalization: vendor a small implementation in `core/canonical.py` rather than take a dep. ~50 lines, eliminates a transitive dep tree.

**Extras:**
- `[postgres]`: `psycopg[binary]>=3`
- `[anthropic]`: `anthropic>=0.40`
- `[fastapi]`: `fastapi`, `uvicorn`
- `[dev]`: `pytest`, `hypothesis`, `mypy`, `pyright`, `ruff`

**Why:** Notebook users `pip install map-protocol` and get a clean environment. Postgres, FastAPI, and Anthropic SDK are opt-in. Vendoring JCS avoids inheriting whatever transitive deps a `pyjcs` package brings — JCS is small enough to own.

---

## §11 — Code style and tooling

**Decision: ruff for everything (lint + format + import sort).** No black, no isort, no flake8.

Configure in `pyproject.toml`: line length 100, target 3.10, all rule families enabled except where noisy. Pre-commit runs ruff + mypy.

**Why:** ruff has consolidated the Python tooling space. One tool, one config, fast. Multiple-tool setups are legacy.

---

## §12 — Versioning and release

**Decision: SemVer for the implementation, separate `SPEC_VERSION` constant for the protocol.**

```python
# map/__init__.py
__version__ = "0.1.0"      # Implementation version (SemVer)
SPEC_VERSION = "0.1"        # MAP spec version this conforms to
```

README documents both: which lib version to pin, which spec version it conforms to.

**Why:** Researchers care which spec they're conforming to for citation and reproducibility. Tying the two together (e.g., lib version 0.1.5 always means spec 0.1) couples bugfix releases to spec freezes. Separating them means the lib can iterate (0.1.0 → 0.1.5 bugfixes) while the spec stays at 0.1; when spec v0.2 lands, lib jumps to 0.2.0.

---

## §13 — Anthropic SDK integration

**Decision: thin wrapper, `map.integrations.anthropic`, exposes one primitive: `wrap_tool_call(map_instance, tool_use_block, registry) -> ToolResult`.**

```python
from anthropic import Anthropic
from map import Map
from map.stores import SQLiteStore
from map.integrations.anthropic import wrap_tool_call

client = Anthropic()
m = Map(store=SQLiteStore("ledger.db"))

@m.reversible(reverser=cancel_order)
def place_order(item_id: str, quantity: int) -> dict: ...

response = client.messages.create(
    model="claude-opus-4-7",
    tools=[place_order.tool_schema],
    messages=[...],
)
for block in response.content:
    if block.type == "tool_use":
        result = wrap_tool_call(m, block, {"place_order": place_order})
```

**Not building:** an agent loop, a framework, a competitor to Pydantic AI / LangGraph / DSPy.

**Why:** Researchers already have agent frameworks. MAP's value is the *primitive* — verifiable action ledger around tool execution. Building a framework dilutes the protocol pitch and competes with tools researchers already use. Stay sharp on "MAP wraps a tool call, you keep your framework."

---

## Locked decisions table

| # | Question | Decision |
|---|----------|----------|
| 1 | Data modeling | Pydantic v2 (`>=2.5,<3`) |
| 2 | Sync vs async | Sync-only at v0.1, async path designed in for v0.2 |
| 3 | Interfaces | `typing.Protocol` with `@runtime_checkable` |
| 4 | Error hierarchy | Layered, single `MapError` root, no stdlib multi-inheritance |
| 5 | Package layout | Flat-ish, public API at `map/__init__.py`, `py.typed` shipped |
| 6 | Testing | pytest + hypothesis + markers |
| 7 | Logging | stdlib `logging`, namespaced `map.*`, `NullHandler` default |
| 8 | Type checking | `mypy --strict` floor, pyright recommended |
| 9 | Python versions | 3.10–3.13 |
| 10 | Dependencies | Pydantic only at core; postgres/anthropic/fastapi as extras; vendor JCS |
| 11 | Style | ruff for everything |
| 12 | Versioning | SemVer for impl, separate `SPEC_VERSION` constant |
| 13 | Anthropic integration | Thin wrapper primitive, no framework |

---

## What this unlocks

The remaining work is mechanical translation against these decisions. No more design choices block the Python build. The next questions are implementation-internal (how to structure module 4's reversal dispatch, what fixture to use for SDK integration test #2) and don't require this kind of meta-deliberation.

Estimated 3 focused days from here to v0.1 Python reference implementation, per the earlier sizing.
