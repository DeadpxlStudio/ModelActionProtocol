// =============================================================================
// State Snapshot — Capture and hash environment state
//
// Before every agent action, the full state is serialized and hashed.
// The serialization is RFC 8785 (JCS) JSON canonicalization, which produces
// byte-identical output across implementations regardless of insertion order,
// number representation quirks, or unicode normalization differences.
//
// SHA-256 over JCS-canonical bytes is the hash used for both state hashes and
// entry hashes. See spec/SPEC.md §5–6.
// =============================================================================

import { createHash } from "crypto";
import canonicalize from "canonicalize";

/**
 * Compute SHA-256 hex digest of a UTF-8 string.
 */
export function sha256(data: string): string {
  return createHash("sha256").update(data).digest("hex");
}

/**
 * RFC 8785 canonicalization of arbitrary JSON-compatible data.
 *
 * Returns the canonical JSON string. For `undefined` input, returns
 * `undefined` (matches JCS behavior — `undefined` is not JSON).
 */
export function serializeState(state: unknown): string {
  return canonicalize(state) ?? "";
}

/**
 * Capture a full state snapshot: deep-clone the value (for storage) and
 * hash its canonical form (for the ledger).
 */
export function captureSnapshot(
  state: unknown
): { serialized: unknown; hash: string } {
  const serialized = state === undefined ? undefined : JSON.parse(JSON.stringify(state));
  const hash = sha256(serializeState(serialized));
  return { serialized, hash };
}

/**
 * Compute a ledger entry hash from its components (per spec §6.2).
 *
 * Hash = SHA-256(JCS({ sequence, action, stateBefore, stateAfter, parentHash, critic }))
 *
 * JCS sorts keys lexicographically, so the order in which we construct the
 * payload object is irrelevant. Cross-language conformance follows from the
 * canonicalization, not from object construction discipline.
 */
export function computeEntryHash(
  sequence: number,
  action: unknown,
  stateBefore: string,
  stateAfter: string,
  parentHash: string,
  critic?: unknown
): string {
  const payload = { sequence, action, stateBefore, stateAfter, parentHash, critic };
  return sha256(serializeState(payload));
}

/**
 * Verify the integrity of a ledger chain (per spec §7).
 * Returns the index of the first corrupted entry if tampered.
 */
export function verifyChain(
  entries: Array<{
    sequence: number;
    action: unknown;
    stateBefore: string;
    stateAfter: string;
    parentHash: string;
    hash: string;
    critic?: unknown;
  }>
): { valid: boolean; corruptedAt?: number } {
  const GENESIS_HASH = "0".repeat(64);

  for (let i = 0; i < entries.length; i++) {
    const entry = entries[i];

    if (entry.sequence !== i) {
      return { valid: false, corruptedAt: i };
    }

    if (i === 0 && entry.parentHash !== GENESIS_HASH) {
      return { valid: false, corruptedAt: 0 };
    }

    if (i > 0 && entry.parentHash !== entries[i - 1].hash) {
      return { valid: false, corruptedAt: i };
    }

    const expectedHash = computeEntryHash(
      entry.sequence,
      entry.action,
      entry.stateBefore,
      entry.stateAfter,
      entry.parentHash,
      entry.critic
    );

    if (entry.hash !== expectedHash) {
      return { valid: false, corruptedAt: i };
    }
  }

  return { valid: true };
}
