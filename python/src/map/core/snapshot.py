"""State snapshots, hashing, and chain verification (sync).

Implements SPEC.md §5–§7. Pure CPU — no I/O. The architectural constraint
(DESIGN.md §2) is that I/O lives only in store classes; this module is part
of the pure-CPU core that the v0.2 async retrofit will reuse unchanged.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any

from .canonical import canonical_bytes, canonical_str

GENESIS_HASH: str = "0" * 64


def sha256_hex(data: bytes | str) -> str:
    """SHA-256 hex digest. Encodes ``str`` to UTF-8 first."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def state_hash(state: Any) -> str:
    """SPEC.md §6.1 — SHA-256 of the JCS canonical encoding of state."""
    return sha256_hex(canonical_bytes(state))


def capture_snapshot(state: Any) -> tuple[Any, str]:
    """Deep-clone a state value (for storage) and hash its canonical form.

    Returns ``(serialized_clone, hash_hex)``. ``None`` state is preserved
    rather than deep-cloned.
    """
    serialized = None if state is None else copy.deepcopy(state)
    return serialized, state_hash(serialized)


def compute_entry_hash(
    sequence: int,
    action: Any,
    state_before: str,
    state_after: str,
    parent_hash: str,
    critic: Any | None = None,
) -> str:
    """SPEC.md §6.2 — SHA-256 of the JCS-canonical encoding of the hash payload.

    Payload fields are exactly: sequence, action, stateBefore, stateAfter,
    parentHash, critic. Their order in the dict literal is irrelevant — JCS
    sorts keys lexicographically.
    """
    payload = {
        "sequence": sequence,
        "action": action,
        "stateBefore": state_before,
        "stateAfter": state_after,
        "parentHash": parent_hash,
        "critic": critic,
    }
    return sha256_hex(canonical_bytes(payload))


def verify_chain(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """SPEC.md §7 — verify a ledger.

    Each entry in ``entries`` must be a dict with at least the chained
    fields (sequence, action, stateBefore, stateAfter, parentHash, hash,
    critic).

    Returns ``{"valid": True}`` on success, or
    ``{"valid": False, "corruptedAt": <int>}`` on the first detected
    corruption.
    """
    for i, entry in enumerate(entries):
        if entry.get("sequence") != i:
            return {"valid": False, "corruptedAt": i}

        if i == 0 and entry.get("parentHash") != GENESIS_HASH:
            return {"valid": False, "corruptedAt": 0}

        if i > 0 and entry.get("parentHash") != entries[i - 1].get("hash"):
            return {"valid": False, "corruptedAt": i}

        expected = compute_entry_hash(
            entry["sequence"],
            entry["action"],
            entry["stateBefore"],
            entry["stateAfter"],
            entry["parentHash"],
            entry.get("critic"),
        )

        if entry.get("hash") != expected:
            return {"valid": False, "corruptedAt": i}

    return {"valid": True}


__all__ = [
    "GENESIS_HASH",
    "canonical_bytes",
    "canonical_str",
    "capture_snapshot",
    "compute_entry_hash",
    "sha256_hex",
    "state_hash",
    "verify_chain",
]
