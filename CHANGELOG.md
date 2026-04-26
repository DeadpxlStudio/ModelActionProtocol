# Changelog

## v0.1.0 (Python reference implementation) — 2026-04-25

First feature-complete release of `map-protocol` on PyPI. Conforms to MAP spec v0.1.0.

**Includes everything from rc1 through rc3** plus the demo artifacts:

- `python/examples/quickstart.ipynb` — narrated Jupyter walkthrough; cross-language conformance proof in the last cell.
- `python/examples/fastapi_app/` — HTTP service wrapping the canonical scenario; demonstrates `asyncio.to_thread()` for sync MAP from async FastAPI handlers (eliminated in v0.2 via `AsyncMap`).
- `python/tests/test_sdk_integration.py` — mocked Anthropic tool-use loop, runs every PR.
- `python/tests/test_sdk_integration_live.py` — same scenario, real API, gated on `ANTHROPIC_API_KEY` (nightly).

**Verification at release:**

- 108 Python tests pass (snapshot, ledger, map, learning, persistence, conformance, SDK integration). 1 Postgres test + 2 live SDK tests skipped on missing env vars.
- 146 TS tests pass under the JCS-migrated reference impl.
- Cross-language fixtures verify byte-identical in both directions across all 6 v0.1 fixtures (semantic + edge cases).
- Wheel built clean; `twine check` passes; clean-venv install works on Python 3.14.
- `npm publish --dry-run` clean for the migrated `@model-action-protocol/core@0.2.0`.

**Distribution:** `pip install map-protocol`. Source: [`python/`](python/). Spec: [`spec/SPEC.md`](spec/SPEC.md).

## v0.1.0-rc3 (Python reference implementation) — 2026-04-25

Two real bugs surfaced while building the FastAPI demo. Both are
correctness fixes, no API changes.

- **SQLite store is now thread-safe.** `SQLiteLedgerStore` opened the
  connection on the main thread; FastAPI handlers run sync MAP code
  inside `asyncio.to_thread()` worker threads, which raised
  `sqlite3.ProgrammingError: SQLite objects created in a thread can only
  be used in that same thread`. Now uses `check_same_thread=False` and a
  re-entrant lock around all DB operations. SQLite itself is thread-safe
  in default builds; the cpython wrapper's check was conservative.
- **`Ledger.append` is now atomic across the in-memory cache and store.**
  The old order — append to cache, then persist — left the cache and
  disk diverged on store failure. New order — persist first, then
  append to cache — means a failed store call leaves the ledger
  unchanged from the caller's perspective (no torn state).

108 Python tests pass + 1 Postgres skipped + 2 live SDK skipped on
missing keys. FastAPI demo smoke test now succeeds end-to-end:
place / flag / rollback / inspect ledger.

## v0.1.0-rc2 (Python reference implementation) — 2026-04-25

Verification-pass fixes from rc1 review. One real behavior change:

- **Rollback semantics locked, behavior changed** (`Map.rollback_to`).
  rc1 silently absorbed reverser failures and marked all entries
  `ROLLED_BACK` regardless. rc2 stops on first failure, propagates the
  exception (`NotReversible` or `ReversalFailed`), and leaves the ledger
  untouched — no entries marked, no `ROLLBACK` record appended. This is
  "all-or-nothing at the ledger layer." Side effects from already-completed
  reversers persist (MAP cannot un-cancel an order); the docstring is now
  explicit about this. Reversers also run in **reverse-sequence order**
  (newest first), matching saga compensation conventions.
- **Decorator stack collisions now warn.** Stacking `@m.reversible` and
  `@m.escalate` on the same function used to silently overwrite the first
  registration. rc2 emits a `WARNING` under logger `map.reversal` on
  overwrite. Pass `replace=True` to silence intentional overwrites.
- **`tool_schema` now resolves PEP 563 string annotations.** The Anthropic
  tool definition shape works for functions with `from __future__ import
  annotations` — primitive types now produce `{"type": "string"}` etc.
  rather than `{}`.
- **`LearningEngine.export_fine_tuning_data` format documented.** The
  export is **MAP-native, not provider-native** — neither OpenAI's
  fine-tune JSONL nor Anthropic's. Docstring now explicit; converters
  may ship in `map.learning.adapters` in a future minor release.
- **`python/.gitignore` added.** Excludes `__pycache__/`, `*.pyc`,
  `.venv/`, build artifacts, and tooling caches. The .pyc files that
  shipped in rc1's commit are removed from tracking.

105 Python tests pass (was 97; +5 verification tests).

## v0.1.0-rc1 (Python reference implementation) — 2026-04-25

Feature-complete v0.1 Python library. Demos + final release prep pending.

- **Surface:** `Map` orchestrator, `Action`, `Ledger`, `LedgerStore` (`MemoryStore`, `SQLiteLedgerStore`, `PostgresLedgerStore`), `Critic` family (`rule_critic`, `llm_critic`, `tiered_critic`), `ReverserRegistry` with `@reversible` / `@compensate` / `@restore` / `@escalate` decorators, `LearningEngine`, `wrap_tool_call` Anthropic integration primitive, layered `MapError` hierarchy.
- **Conformance:** Verifies every `spec/fixtures/v0.1/*.json` byte-for-byte under the vendored JCS canonicalization; Python-generated ledgers verify under the TS reference impl (`src/__tests__/python-output-conformance.test.ts`).
- **Tests:** 97 passing on Python (snapshot, ledger, map, learning, persistence, conformance) + 146 on TS = 243 total.
- **Pending for 0.1.0 final:** Jupyter notebook demo (`python/examples/quickstart.ipynb`), FastAPI mini-app (`python/examples/fastapi_app/`), mocked + live SDK integration tests, PyPI publish.

If the demos surface API friction, expect a `v0.1.0-rc2` before `v0.1.0` ships to PyPI.

## v0.1 frozen — 2026-04-25

The protocol specification, conformance fixtures, plan, and Python design choices are frozen at v0.1. Future minor changes to any of these require a new spec version (`v0.2`) and a corresponding fixture directory (`spec/fixtures/v0.2/`).

**Frozen artifacts:**
- `spec/SPEC.md` v0.1.0 — wire format, JCS canonicalization (RFC 8785), §6.4 worked example with pinned hash `25d29bc25a183ebdb29b70b6a03ed2ad8d31033d1fb6347f656b21d7e9efb650`.
- `spec/fixtures/v0.1/` — 6 conformance fixtures (pass-only, corrected-mid-chain, flagged-halt, rollback-and-resume, learning-patterns, edge-cases). Immutable.
- `docs/v0.1-plan.md` — implementation plan for the Python reference SDK.
- `python/DESIGN.md` — Python implementation design choices (Pydantic v2, sync-all-the-way-down, Protocol interfaces, layered errors, vendored JCS).

**Verification at freeze:**
- TS test suite: 146 passing (61 original + 53 conformance + 32 reverse-direction).
- Python test suite: 73 passing (12 snapshot + 11 ledger + 50 conformance) under the pre-refactor `model_action_protocol/` package; refactor to `map/` package follows.
- Cross-language conformance proven byte-identical in both directions across all 6 v0.1 fixtures.

**Local git tags created:** `v0.1-spec-frozen`, `v0.1-design-frozen`, `v0.1-plan-frozen`. Pushing the tags is a separate decision.

**Pending:** Python reference implementation refactor (sync conversion, package rename to `map/`, vendor JCS, layered exceptions, py.typed). See `docs/v0.1-plan.md`.

## 0.2.0 (2026-04-25)

**Breaking change.** Adopted RFC 8785 (JCS) for JSON canonicalization. Hash outputs change for every entry; ledgers produced by 0.1.x will not verify under 0.2.0 and vice versa. This is a one-time migration to align with the new spec at `spec/SPEC.md`.

### Why

The 0.1.x line used a custom recursive key-sort canonicalization. The Python SDK (forthcoming) and any future ports require a standardized canonicalization to guarantee byte-identical hashes across languages. RFC 8785 is the standard answer; both `canonicalize` (npm) and `jcs` (PyPI) implement it. Specifying "MAP uses RFC 8785" in the spec replaces a multi-page edge-case appendix on numbers, unicode, key ordering, and null handling — and gives the protocol a real standards anchor.

### Changes

- **Added.** RFC 8785 canonicalization via `canonicalize` (npm dependency).
- **Added.** `spec/SPEC.md` — standalone wire-format specification, version 0.1.0. Both this implementation and the forthcoming Python SDK conform to it.
- **Removed.** `MAPConfig.serializeState` and `captureSnapshot`'s `customSerializer` argument. Custom serializers conflict with the JCS conformance requirement; users who need pre-processing should transform state before passing it to `MAP.execute()`.
- **Hash format.** Entry-hash payloads are now JCS-canonicalized (lexicographic key order). State hashes were already key-sorted — values are unchanged for typical JSON state.

### Migration

Existing user databases are no longer verifiable under 0.2.0. There is no migration path that preserves existing hashes — the canonicalization rule changed by design. Users with persisted ledgers should:

1. Export the existing ledger as JSON via `map.exportLedger()` while still on 0.1.x.
2. Archive the export with a note that it is a "legacy 0.1.x" artifact.
3. Restart the ledger under 0.2.0 from scratch.

If preserving the audit trail across the version boundary is critical, pin to 0.1.2 until you can replay the ledger.

## 0.1.0 (2026-04-09)

Initial release of `@model-action-protocol/core`.

### Features

- **Cryptographic Provenance Ledger** — SHA-256 hash-chained, append-only action log with full state snapshots
- **Self-Healing Critic Loop** — Tiered model routing with PASS / CORRECTED / FLAGGED verdicts
- **Reversal Schema** — COMPENSATE, RESTORE, and ESCALATE strategies for typed rollback
- **State Rollback** — One-click revert to any prior ledger entry, rollback logged as provenance
- **Multi-Agent Provenance (KYA)** — Agent identity, authorization grants, ephemeral lifecycle tracking
- **Human-on-the-Loop Approval** — Pending/approved/rejected workflow for flagged actions
- **Learning Engine** — Rule extraction, fine-tuning export, and agent memory from correction history
- **Tool Builder** — `defineTool`, `defineRestoreTool`, `defineCompensateTool`, `defineEscalateTool` helpers
- **Real-Time Events** — Event-driven architecture for UI integration
