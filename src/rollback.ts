// =============================================================================
// MAP Rollback — State machine revert from ledger snapshots
//
// Because the ledger captures the full serialized state before every action,
// rolling back is just "restore the snapshot from entry N."
//
// The rollback itself is logged to the ledger — you can audit the undo.
// This makes the rollback operation part of the provenance chain, not
// something that happens outside of it.
//
// Key insight: rollback is not "undo." Undo implies removing history.
// Rollback preserves the full history (including the mistake) and adds
// a new entry showing the revert. The audit trail is always complete.
// =============================================================================

import type { Ledger } from "./ledger.js";
import type { LedgerEntry } from "./protocol.js";

export interface RollbackResult {
  /** The restored state */
  state: unknown;
  /** Number of entries marked as ROLLED_BACK */
  entriesReverted: number;
  /** The ledger entry for the rollback action itself */
  rollbackEntry: LedgerEntry;
}

/**
 * Execute a rollback to a specific ledger entry.
 *
 * 1. Retrieves the target entry's pre-action state snapshot
 * 2. Marks all entries from target onwards as ROLLED_BACK
 * 3. Appends a ROLLBACK entry to the ledger (provenance of the undo)
 * 4. Returns the restored state for the caller to apply
 *
 * The caller is responsible for actually applying the restored state
 * to their environment. MAP captures the intent and provenance;
 * the application layer handles the mutation.
 */
export function executeRollback(
  ledger: Ledger,
  targetId: string
): RollbackResult {
  const entry = ledger.getEntry(targetId);
  if (!entry) {
    throw new Error(`Cannot rollback: entry ${targetId} not found`);
  }

  if (entry.status === "ROLLED_BACK") {
    throw new Error(
      `Cannot rollback: entry ${targetId} is already rolled back`
    );
  }

  const { state, entriesReverted } = ledger.rollbackTo(targetId);

  // The rollback entry is the last one appended by ledger.rollbackTo()
  const entries = ledger.getEntries();
  const rollbackEntry = entries[entries.length - 1];

  return {
    state,
    entriesReverted,
    rollbackEntry,
  };
}

/**
 * Find the most recent entry that was FLAGGED or CORRECTED.
 * Useful for "rollback to last known good state" UX.
 */
export function findLastProblem(
  ledger: Ledger
): LedgerEntry | undefined {
  const entries = ledger.getEntries();
  for (let i = entries.length - 1; i >= 0; i--) {
    const entry = entries[i];
    if (
      entry.status === "ACTIVE" &&
      (entry.critic.verdict === "FLAGGED" || entry.critic.verdict === "CORRECTED")
    ) {
      return entry;
    }
  }
  return undefined;
}

/**
 * Find the last entry before a problem occurred.
 * This is the entry you'd want to rollback TO.
 */
export function findSafePoint(
  ledger: Ledger
): LedgerEntry | undefined {
  const problem = findLastProblem(ledger);
  if (!problem) return undefined;

  const entries = ledger.getEntries();
  const problemIdx = entries.findIndex((e) => e.id === problem.id);
  if (problemIdx <= 0) return undefined;

  // Return the entry before the problem
  return entries[problemIdx - 1];
}
