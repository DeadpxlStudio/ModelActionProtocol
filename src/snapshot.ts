// =============================================================================
// State Snapshot — Capture and hash environment state
//
// Before every agent action, the full state is serialized and hashed.
// This enables tamper-evident logging and instant rollback to any prior state.
//
// Uses Web Crypto API for SHA-256 — native, no dependencies.
// =============================================================================

import { createHash } from "crypto";

/**
 * Compute SHA-256 hash of arbitrary data.
 * Uses Node.js crypto for server-side (matches Claude Code's approach
 * of keeping core operations native with zero external dependencies).
 */
export function sha256(data: string): string {
  return createHash("sha256").update(data).digest("hex");
}

/**
 * Serialize state to a deterministic string.
 * Keys are sorted to ensure identical objects produce identical hashes
 * regardless of property insertion order.
 */
export function serializeState(state: unknown): string {
  return JSON.stringify(state, Object.keys(state as object).sort());
}

/**
 * Capture a full state snapshot: serialize + hash.
 * Returns both the serialized state (for rollback) and its hash (for the ledger).
 */
export function captureSnapshot(
  state: unknown,
  customSerializer?: (state: unknown) => string
): { serialized: unknown; hash: string } {
  const serialize = customSerializer ?? serializeState;
  const serialized = JSON.parse(JSON.stringify(state)); // deep clone
  const hash = sha256(serialize(state));
  return { serialized, hash };
}

/**
 * Compute a ledger entry hash from its components.
 * This chains entries together — changing any prior entry invalidates
 * all subsequent hashes, making the ledger tamper-evident.
 *
 * Hash = SHA-256(sequence | action_json | stateBefore | stateAfter | parentHash)
 */
export function computeEntryHash(
  sequence: number,
  action: unknown,
  stateBefore: string,
  stateAfter: string,
  parentHash: string
): string {
  const payload = [
    sequence.toString(),
    JSON.stringify(action),
    stateBefore,
    stateAfter,
    parentHash,
  ].join("|");
  return sha256(payload);
}

/**
 * Verify the integrity of a ledger chain.
 * Returns true if all hashes are valid and properly chained.
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
  }>
): { valid: boolean; corruptedAt?: number } {
  for (let i = 0; i < entries.length; i++) {
    const entry = entries[i];
    const expectedHash = computeEntryHash(
      entry.sequence,
      entry.action,
      entry.stateBefore,
      entry.stateAfter,
      entry.parentHash
    );

    if (entry.hash !== expectedHash) {
      return { valid: false, corruptedAt: i };
    }

    // Verify chain linkage (skip genesis entry)
    if (i > 0 && entry.parentHash !== entries[i - 1].hash) {
      return { valid: false, corruptedAt: i };
    }
  }

  return { valid: true };
}
