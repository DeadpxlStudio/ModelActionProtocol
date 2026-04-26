"""Generate Python-written ledgers for the reverse-direction conformance test.

These fixtures are written by Python's Ledger class and committed under
`python/tests/fixtures/python-generated/`. The TS test
`python-output-conformance.test.ts` loads them and asserts every chain
verifies under the TS implementation. Together with the TS→Python direction
already covered by `spec/fixtures/v0.1/`, this closes the cross-language loop.

Run:
    python python/scripts/generate_python_fixtures.py

Determinism: UUIDs are derived from a seeded counter and timestamps are
fixed, so regenerating produces byte-identical output. To re-pin (e.g., for
v0.2), bump the SEED constant.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow running as a script without installation
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from map import (  # noqa: E402
    GENESIS_HASH,
    SPEC_VERSION,
    Action,
    CompensatingAction,
    CriticCorrection,
    CriticResult,
    LedgerEntry,
    LedgerSnapshots,
    LedgerStats,
    ReversalSchema,
    capture_snapshot,
    compute_entry_hash,
)

ActionRecord = Action  # spec name; kept for parity with TS generator

OUTPUT_DIR = HERE.parent / "tests" / "fixtures" / "python-generated"
SEED = "map-v0.1-python-fixtures"
FIXED_TIMESTAMP = "2026-04-25T00:00:00.000Z"

_uuid_counter = 0


def _reset_uuid(start: int) -> None:
    global _uuid_counter
    _uuid_counter = start


def det_uuid() -> str:
    """Deterministic UUIDv4-shaped string."""
    global _uuid_counter
    h = hashlib.sha256(f"{SEED}:{_uuid_counter}".encode()).hexdigest()
    _uuid_counter += 1
    return f"{h[0:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}"


def build_entry(
    prev: LedgerEntry | None,
    action: ActionRecord,
    state_before: Any,
    state_after: Any,
    critic: CriticResult,
    status: str = "ACTIVE",
) -> LedgerEntry:
    sequence = 0 if prev is None else prev.sequence + 1
    parent_hash = GENESIS_HASH if prev is None else prev.hash

    before_clone, before_hash = capture_snapshot(state_before)
    after_clone, after_hash = capture_snapshot(state_after)

    action_dump = action.model_dump(by_alias=True, exclude_none=True)
    critic_dump = critic.model_dump(by_alias=True, exclude_none=True)

    entry_hash = compute_entry_hash(
        sequence=sequence,
        action=action_dump,
        state_before=before_hash,
        state_after=after_hash,
        parent_hash=parent_hash,
        critic=critic_dump,
    )

    return LedgerEntry(
        id=det_uuid(),
        sequence=sequence,
        timestamp=FIXED_TIMESTAMP,
        action=action,
        stateBefore=before_hash,
        stateAfter=after_hash,
        snapshots=LedgerSnapshots(before=before_clone, after=after_clone),
        parentHash=parent_hash,
        hash=entry_hash,
        critic=critic,
        status=status,  # type: ignore[arg-type]
    )


def stats_for(entries: list[LedgerEntry]) -> LedgerStats:
    return LedgerStats(
        total=len(entries),
        committed=sum(
            1
            for e in entries
            if e.status == "ACTIVE" and e.action.tool != "ROLLBACK"
        ),
        rolledBack=sum(1 for e in entries if e.status == "ROLLED_BACK"),
        corrections=sum(1 for e in entries if e.critic.verdict == "CORRECTED"),
        flags=sum(1 for e in entries if e.critic.verdict == "FLAGGED"),
    )


def write_fixture(name: str, entries: list[LedgerEntry]) -> None:
    fixture = {
        "protocol": "map",
        "version": f"{SPEC_VERSION}.0",
        "entries": [e.model_dump(by_alias=True, exclude_none=True) for e in entries],
        "stats": stats_for(entries).model_dump(by_alias=True),
    }
    path = OUTPUT_DIR / name
    path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {name} ({len(entries)} entries)")


def fixture_pass_only_3() -> None:
    _reset_uuid(0)
    prev: LedgerEntry | None = None
    entries: list[LedgerEntry] = []
    state: dict[str, Any] = {"counter": 0}
    for v in [1, 2, 3]:
        nxt = {"counter": v}
        e = build_entry(
            prev,
            ActionRecord(tool="increment", input={"by": 1}, output={"ok": True}),
            state,
            nxt,
            CriticResult(verdict="PASS", reason="counter increment is well-formed"),
        )
        entries.append(e)
        prev = e
        state = nxt
    write_fixture("pass-only-3-actions.json", entries)


def fixture_corrected_mid_chain() -> None:
    _reset_uuid(100)
    prev: LedgerEntry | None = None
    entries: list[LedgerEntry] = []

    s0: dict[str, Any] = {"balance": 100}
    s1: dict[str, Any] = {"balance": 90}
    prev = build_entry(
        prev,
        ActionRecord(tool="debit", input={"amount": 10}, output={"ok": True}),
        s0,
        s1,
        CriticResult(verdict="PASS", reason="debit within available balance"),
    )
    entries.append(prev)

    s2: dict[str, Any] = {"balance": 85}
    prev = build_entry(
        prev,
        ActionRecord(tool="debit", input={"amount": 5}, output={"ok": True}),
        s1,
        s2,
        CriticResult(
            verdict="CORRECTED",
            reason="original debit of 50 exceeded balance; corrected to 5",
            correction=CriticCorrection(tool="debit", input={"amount": 5}),
        ),
    )
    entries.append(prev)

    s3: dict[str, Any] = {"balance": 80}
    prev = build_entry(
        prev,
        ActionRecord(tool="debit", input={"amount": 5}, output={"ok": True}),
        s2,
        s3,
        CriticResult(verdict="PASS", reason="ok"),
    )
    entries.append(prev)

    write_fixture("corrected-mid-chain.json", entries)


def fixture_flagged_with_reversal_schema() -> None:
    """Includes a ReversalSchema in the action — exercises optional nested fields."""
    _reset_uuid(200)
    prev: LedgerEntry | None = None
    entries: list[LedgerEntry] = []

    s0 = {"account": {"id": "A1"}}
    prev = build_entry(
        prev,
        ActionRecord(
            tool="wireTransfer",
            input={"amount": 100000, "to": "external"},
            output=None,
            reversalStrategy="ESCALATE",
        ),
        s0,
        s0,
        CriticResult(
            verdict="FLAGGED",
            reason="wire transfer over $50k requires human approval",
        ),
    )
    entries.append(prev)
    write_fixture("flagged-with-reversal.json", entries)


def fixture_edge_cases() -> None:
    """Mirrors the TS edge-cases fixture: unicode (NFC), nesting, empty, large."""
    _reset_uuid(300)
    prev: LedgerEntry | None = None
    entries: list[LedgerEntry] = []

    prev = build_entry(
        prev,
        ActionRecord(
            tool="logCustomer",
            input={"name": "café", "emoji": "🥐", "chinese": "你好"},
            output={"ok": True},
        ),
        {"customers": []},
        {"customers": [{"name": "café"}]},
        CriticResult(verdict="PASS", reason="unicode preserved through canonicalization"),
    )
    entries.append(prev)

    prev = build_entry(
        prev,
        ActionRecord(tool="noop", input={}, output={}),
        {"customers": [{"name": "café"}]},
        {"customers": [{"name": "café"}]},
        CriticResult(verdict="PASS", reason="no-op"),
    )
    entries.append(prev)

    deep_before = {"a": {"b": {"c": {"d": {"e": {"f": {"value": 0}}}}}}}
    deep_after = {"a": {"b": {"c": {"d": {"e": {"f": {"value": 1}}}}}}}
    prev = build_entry(
        prev,
        ActionRecord(
            tool="deepUpdate",
            input={"path": "a.b.c.d.e.f.value", "to": 1},
            output={"ok": True},
        ),
        deep_before,
        deep_after,
        CriticResult(verdict="PASS", reason="deep nesting preserved"),
    )
    entries.append(prev)

    items = [
        {
            "id": f"item-{i:04d}",
            "label": f"Description for item {i}",
            "tags": ["alpha", "beta", "gamma"],
            "score": i * 0.5,
        }
        for i in range(200)
    ]
    prev = build_entry(
        prev,
        ActionRecord(
            tool="bulkImport",
            input={"count": len(items)},
            output={"imported": len(items)},
        ),
        {"items": []},
        {"items": items},
        CriticResult(verdict="PASS", reason="bulk import of 200 items"),
    )
    entries.append(prev)

    write_fixture("edge-cases.json", entries)


def fixture_with_reversal_schema_full() -> None:
    """A COMPENSATE action exercising the full ReversalSchema with inputMapping."""
    _reset_uuid(400)
    prev: LedgerEntry | None = None
    entries: list[LedgerEntry] = []

    schema = ReversalSchema(
        strategy="COMPENSATE",
        compensatingAction=CompensatingAction(
            tool="issueCreditMemo",
            inputMapping={"amount": "amount", "customerId": "customerId"},
        ),
        description="duplicate invoice → credit memo",
    )
    prev = build_entry(
        prev,
        ActionRecord(
            tool="issueInvoice",
            input={"amount": 250, "customerId": "C-77"},
            output={"invoiceId": "INV-1"},
            reversalStrategy=schema.strategy,
        ),
        {"invoices": []},
        {"invoices": [{"id": "INV-1", "amount": 250}]},
        CriticResult(verdict="PASS", reason="invoice issued"),
    )
    entries.append(prev)
    write_fixture("compensate-reversal.json", entries)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"generating Python fixtures at {OUTPUT_DIR}")
    fixture_pass_only_3()
    fixture_corrected_mid_chain()
    fixture_flagged_with_reversal_schema()
    fixture_edge_cases()
    fixture_with_reversal_schema_full()
    print("done.")


if __name__ == "__main__":
    main()
