"""Cross-language conformance tests.

Loads frozen fixtures from `spec/fixtures/v0.1/` (TS-generated) and verifies
them under the Python implementation. If any fixture fails to verify, the
two implementations have diverged and one of them violates SPEC.md.

These fixtures are immutable: a future spec version produces a new directory
(spec/fixtures/v0.2/), and the v0.1 directory remains for regression
testing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from map import (
    GENESIS_HASH,
    compute_entry_hash,
    state_hash,
    verify_chain,
)

FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent.parent / "spec" / "fixtures" / "v0.1"
)

LEDGER_FIXTURES = [
    "pass-only-3-actions.json",
    "corrected-mid-chain.json",
    "flagged-halt.json",
    "rollback-and-resume.json",
    "learning-patterns.json",
    "edge-cases.json",
]


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


# ─── Per-fixture verification ───────────────────────────────────────────────


@pytest.mark.parametrize("name", LEDGER_FIXTURES)
def test_fixture_declares_protocol_and_version(name: str) -> None:
    fx = _load(name)
    assert fx["protocol"] == "map"
    assert fx["version"] == "0.1.0"


@pytest.mark.parametrize("name", LEDGER_FIXTURES)
def test_fixture_verifies_as_valid_chain(name: str) -> None:
    fx = _load(name)
    assert verify_chain(fx["entries"]) == {"valid": True}


@pytest.mark.parametrize("name", LEDGER_FIXTURES)
def test_fixture_recomputes_each_entry_hash(name: str) -> None:
    fx = _load(name)
    for entry in fx["entries"]:
        expected = compute_entry_hash(
            entry["sequence"],
            entry["action"],
            entry["stateBefore"],
            entry["stateAfter"],
            entry["parentHash"],
            entry.get("critic"),
        )
        assert entry["hash"] == expected, (
            f"hash mismatch in {name} at sequence {entry['sequence']}: "
            f"stored={entry['hash']!r} expected={expected!r}"
        )


@pytest.mark.parametrize("name", LEDGER_FIXTURES)
def test_fixture_state_hashes_match_snapshots(name: str) -> None:
    fx = _load(name)
    for entry in fx["entries"]:
        assert entry["stateBefore"] == state_hash(entry["snapshots"]["before"])
        assert entry["stateAfter"] == state_hash(entry["snapshots"]["after"])


# ─── Negative tests — mutation detection ────────────────────────────────────


@pytest.mark.parametrize("name", LEDGER_FIXTURES)
def test_mutation_of_entry_hash_detected(name: str) -> None:
    fx = _load(name)
    if not fx["entries"]:
        return
    target = min(1, len(fx["entries"]) - 1)
    mutated = [
        {**e, "hash": "f" * 64} if i == target else e
        for i, e in enumerate(fx["entries"])
    ]
    result = verify_chain(mutated)
    assert result["valid"] is False
    # Hash-integrity check at the target fires before chain-linkage at the
    # next index, so corruption is reported at the target.
    assert result["corruptedAt"] == target


@pytest.mark.parametrize("name", LEDGER_FIXTURES)
def test_mutation_of_action_detected(name: str) -> None:
    fx = _load(name)
    if not fx["entries"]:
        return
    target = 0
    mutated = []
    for i, e in enumerate(fx["entries"]):
        if i == target:
            ee = {**e, "action": {**e["action"], "tool": "tampered"}}
            mutated.append(ee)
        else:
            mutated.append(e)
    result = verify_chain(mutated)
    assert result == {"valid": False, "corruptedAt": target}


@pytest.mark.parametrize("name", LEDGER_FIXTURES)
def test_mutation_of_critic_verdict_detected(name: str) -> None:
    fx = _load(name)
    if not fx["entries"]:
        return
    target = 0
    if fx["entries"][target]["critic"]["verdict"] == "PASS":
        # Skip — flipping PASS to PASS is a no-op
        return
    mutated = []
    for i, e in enumerate(fx["entries"]):
        if i == target:
            ee = {**e, "critic": {**e["critic"], "verdict": "PASS"}}
            mutated.append(ee)
        else:
            mutated.append(e)
    result = verify_chain(mutated)
    assert result == {"valid": False, "corruptedAt": target}


def test_mutation_of_genesis_parent_hash_detected() -> None:
    fx = _load("pass-only-3-actions.json")
    mutated = [
        {**e, "parentHash": "1" * 64} if i == 0 else e
        for i, e in enumerate(fx["entries"])
    ]
    result = verify_chain(mutated)
    assert result == {"valid": False, "corruptedAt": 0}


def test_mutation_of_sequence_gap_detected() -> None:
    fx = _load("pass-only-3-actions.json")
    mutated = [
        {**e, "sequence": 99} if i == 1 else e
        for i, e in enumerate(fx["entries"])
    ]
    result = verify_chain(mutated)
    assert result == {"valid": False, "corruptedAt": 1}


# ─── Structural tampering — order, insertion, deletion ──────────────────────


def test_entry_swap_detected() -> None:
    fx = _load("pass-only-3-actions.json")
    swapped = list(fx["entries"])
    swapped[0], swapped[1] = swapped[1], swapped[0]
    result = verify_chain(swapped)
    assert result["valid"] is False
    # Swapped entry at index 0 has sequence=1 → continuity fails immediately.
    assert result["corruptedAt"] == 0


def test_entry_insertion_detected() -> None:
    fx = _load("pass-only-3-actions.json")
    fake = {
        **fx["entries"][0],
        "id": "11111111-1111-4111-8111-111111111111",
        "sequence": 1,
        "action": {"tool": "injected", "input": {}, "output": None},
        "hash": "f" * 64,
    }
    tampered = [fx["entries"][0], fake]
    for i, e in enumerate(fx["entries"][1:]):
        tampered.append({**e, "sequence": i + 2})
    result = verify_chain(tampered)
    assert result["valid"] is False
    # Injected entry at index 1 has a fabricated hash → integrity fails there.
    assert result["corruptedAt"] == 1


def test_entry_deletion_detected() -> None:
    fx = _load("pass-only-3-actions.json")
    truncated = [fx["entries"][0], *fx["entries"][2:]]
    result = verify_chain(truncated)
    assert result["valid"] is False
    # Index 1 now holds the original entry-2 (sequence=2) → continuity fails.
    assert result["corruptedAt"] == 1


# ─── Unicode normalization sensitivity ──────────────────────────────────────


def test_nfc_and_nfd_strings_produce_different_hashes() -> None:
    """Spec mandates JCS without normalization. Callers passing NFD vs NFC
    for the 'same' string MUST produce different hashes — this test pins that
    behavior so users don't accidentally rely on silent normalization.
    """
    import unicodedata

    from map import state_hash

    nfc = unicodedata.normalize("NFC", "café")
    nfd = unicodedata.normalize("NFD", "café")
    assert nfc != nfd
    assert unicodedata.normalize("NFC", nfc) == unicodedata.normalize("NFC", nfd)
    assert state_hash({"name": nfc}) != state_hash({"name": nfd})


# ─── LearningEngine fingerprint conformance ─────────────────────────────────


def test_learning_fingerprints_match_documented_formula() -> None:
    """SPEC.md §6.3 — fingerprint = SHA-256(verdict:tool:correctionTool|"none")."""
    fx = _load("learning-patterns.json")
    assert "expectedPatterns" in fx
    assert len(fx["expectedPatterns"]) > 0

    for expected in fx["expectedPatterns"]:
        # Find a matching entry to derive inputs
        matching = [
            e
            for e in fx["entries"]
            if e["action"]["tool"] == expected["tool"]
            and e["critic"]["verdict"] in ("CORRECTED", "FLAGGED")
        ]
        assert matching, f"no matching entry for tool {expected['tool']}"
        e = matching[0]
        correction_tool = (e["critic"].get("correction") or {}).get("tool", "none")
        formula_input = f"{e['critic']['verdict']}:{e['action']['tool']}:{correction_tool}"
        computed = hashlib.sha256(formula_input.encode("utf-8")).hexdigest()
        assert expected["fingerprint"] == computed, (
            f"fingerprint mismatch for tool {expected['tool']}: "
            f"expected={expected['fingerprint']} computed={computed}"
        )


# ─── Fixture directory ──────────────────────────────────────────────────────


def test_fixture_directory_contains_documented_files() -> None:
    found = sorted(p.name for p in FIXTURES_DIR.glob("*.json"))
    assert found == sorted(LEDGER_FIXTURES)
