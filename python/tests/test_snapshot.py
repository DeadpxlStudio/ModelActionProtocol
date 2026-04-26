"""Unit tests for snapshot.py — JCS canonicalization and hashing.

The most important test here is `test_canonical_json_known_hash`: it asserts
that the SHA-256 of the worked example in SPEC.md §6.4 matches the documented
hex digest. If this fails, the Python impl is not JCS-conforming and every
other conformance test will follow.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from map import (
    GENESIS_HASH,
    canonical_str,
    capture_snapshot,
    compute_entry_hash,
    sha256_hex,
    state_hash,
    verify_chain,
)


def test_pyproject_and_runtime_version_match() -> None:
    """Regression — pyproject.toml version MUST match map.__version__.

    Caught after v0.1.1 shipped to PyPI with metadata 0.1.1 but
    `import map; map.__version__` returning 0.1.0. The mismatch was
    cosmetic — the library worked — but it misled anyone introspecting
    the installed package, so v0.1.1 was yanked. This test pins the
    invariant so it can't recur silently.
    """
    import tomllib

    from map import __version__

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    with pyproject.open("rb") as f:
        meta_version = tomllib.load(f)["project"]["version"]
    assert meta_version == __version__, (
        f"pyproject.toml version {meta_version!r} != map.__version__ {__version__!r}; "
        "update src/map/_version.py to match before publishing"
    )


# ─── §6.4 Worked example — the load-bearing test ────────────────────────────

def test_canonical_json_known_hash():
    """Pin the spec's worked example.

    These literal hashes are copied from `Open Source/spec/SPEC.md` §6.4.
    If you change either side, change both — they are coupled by design.
    The TS test of the same name asserts the identical literals.
    """
    null_state_hash = state_hash(None)
    # SPEC.md §6.4: state used = null → SHA-256(JCS(null)) = SHA-256("null")
    assert (
        null_state_hash
        == "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b"
    )

    entry_hash = compute_entry_hash(
        sequence=0,
        action={"tool": "ping", "input": {}, "output": "pong"},
        state_before=null_state_hash,
        state_after=null_state_hash,
        parent_hash=GENESIS_HASH,
        critic={"verdict": "PASS", "reason": "ok"},
    )
    # SPEC.md §6.4: documented entry hash for the worked example.
    assert (
        entry_hash
        == "25d29bc25a183ebdb29b70b6a03ed2ad8d31033d1fb6347f656b21d7e9efb650"
    )


def test_canonical_json_payload_string():
    """SPEC.md §6.4 — canonical bytes form (lex key order, no whitespace)."""
    null_state_hash = state_hash(None)
    payload = {
        "sequence": 0,
        "action": {"tool": "ping", "input": {}, "output": "pong"},
        "stateBefore": null_state_hash,
        "stateAfter": null_state_hash,
        "parentHash": GENESIS_HASH,
        "critic": {"verdict": "PASS", "reason": "ok"},
    }
    expected = (
        '{"action":{"input":{},"output":"pong","tool":"ping"},'
        '"critic":{"reason":"ok","verdict":"PASS"},'
        '"parentHash":"0000000000000000000000000000000000000000000000000000000000000000",'
        '"sequence":0,'
        '"stateAfter":"74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b",'
        '"stateBefore":"74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b"}'
    )
    assert canonical_str(payload) == expected


# ─── sha256_hex ─────────────────────────────────────────────────────────────


def test_sha256_hex_str_and_bytes_agree():
    assert sha256_hex("hello") == sha256_hex(b"hello")


def test_sha256_hex_known_value():
    # Known: SHA-256("") = e3b0c44...
    assert sha256_hex("") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


# ─── canonicalization determinism ───────────────────────────────────────────


def test_canonical_str_sorts_keys_recursively():
    a = {"z": 1, "a": 2, "m": {"y": 3, "x": 4}}
    b = {"a": 2, "m": {"x": 4, "y": 3}, "z": 1}
    assert canonical_str(a) == canonical_str(b)


def test_canonical_str_preserves_array_order():
    assert canonical_str([3, 1, 2]) == "[3,1,2]"


def test_canonical_str_handles_primitives():
    assert canonical_str(42) == "42"
    assert canonical_str("hello") == '"hello"'
    assert canonical_str(True) == "true"
    assert canonical_str(None) == "null"


# ─── state_hash ─────────────────────────────────────────────────────────────


def test_state_hash_deterministic_across_key_order():
    a = {"counter": 5, "name": "x"}
    b = {"name": "x", "counter": 5}
    assert state_hash(a) == state_hash(b)


# ─── RFC 8785 §3.2.2.3 — integer-valued float regression ────────────────────


def test_integer_valued_float_hashes_same_as_int():
    """Pin RFC 8785 §3.2.2.3 number serialization.

    JS's `JSON.stringify(1.0)` is `"1"`, not `"1.0"`. Our canonicalization
    must match. If this test fails, the cross-language hash protocol is
    silently broken — every TS-side ledger with a whole-number float field
    will hash differently in Python.
    """
    assert state_hash({"quantity": 1.0}) == state_hash({"quantity": 1})
    assert state_hash({"price": 0.0}) == state_hash({"price": 0})
    # Negative zero must collapse to zero.
    assert state_hash({"x": -0.0}) == state_hash({"x": 0})
    # Non-integer floats must NOT collapse — 0.5 stays 0.5.
    assert state_hash({"x": 0.5}) != state_hash({"x": 1})


def test_canonical_rejects_nan_and_infinity():
    """RFC 8785 §3.2.2.3 forbids NaN and ±Infinity in canonical JSON."""
    import math

    from map import canonical_str
    from map.exceptions import ValidationError

    with pytest.raises(ValidationError, match="NaN"):
        canonical_str({"x": math.nan})
    with pytest.raises(ValidationError, match="Infinity"):
        canonical_str({"x": math.inf})
    with pytest.raises(ValidationError, match="Infinity"):
        canonical_str({"x": -math.inf})


def test_canonical_rejects_unsafe_integer():
    """Integers outside JS safe range cannot round-trip through cross-language hashing."""
    from map import canonical_str
    from map.exceptions import ValidationError

    safe_max = (1 << 53) - 1
    # Safe values pass.
    assert canonical_str({"n": safe_max}) == f'{{"n":{safe_max}}}'
    assert canonical_str({"n": -safe_max}) == f'{{"n":-{safe_max}}}'
    # One past safe is rejected.
    with pytest.raises(ValidationError, match="safe range"):
        canonical_str({"n": safe_max + 1})
    with pytest.raises(ValidationError, match="safe range"):
        canonical_str({"n": -(safe_max + 1)})


def test_capture_snapshot_returns_clone_and_hash():
    state = {"items": [1, 2, 3]}
    serialized, h = capture_snapshot(state)
    assert serialized == state
    assert serialized is not state  # deep clone
    assert h == state_hash(state)


# ─── verify_chain — basic ───────────────────────────────────────────────────


def test_verify_chain_empty_is_valid():
    assert verify_chain([]) == {"valid": True}


def test_verify_chain_detects_bad_genesis():
    entry = {
        "sequence": 0,
        "action": {"tool": "x", "input": {}, "output": None},
        "stateBefore": sha256_hex("a"),
        "stateAfter": sha256_hex("b"),
        "parentHash": "1" * 64,  # not genesis
        "hash": "irrelevant",
    }
    result = verify_chain([entry])
    assert result == {"valid": False, "corruptedAt": 0}


def test_verify_chain_detects_sequence_gap():
    e0_action = {"tool": "x", "input": {}, "output": None}
    e0_hash = compute_entry_hash(
        0, e0_action, sha256_hex("a"), sha256_hex("b"), GENESIS_HASH, None
    )
    e0 = {
        "sequence": 0,
        "action": e0_action,
        "stateBefore": sha256_hex("a"),
        "stateAfter": sha256_hex("b"),
        "parentHash": GENESIS_HASH,
        "hash": e0_hash,
    }
    e1_bad = {**e0, "sequence": 99}
    assert verify_chain([e0, e1_bad]) == {"valid": False, "corruptedAt": 1}
