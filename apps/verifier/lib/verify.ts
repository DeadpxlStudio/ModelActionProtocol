import { verifyChain, MAP_VERSION, MAP_PROTOCOL } from "@model-action-protocol/core";
import type { LedgerEntry } from "@model-action-protocol/core";

export interface ExportedLedger {
  protocol?: string;
  version?: string;
  entries: LedgerEntry[];
  stats?: {
    total: number;
    committed: number;
    rolledBack: number;
    corrections: number;
    flags: number;
  };
}

export interface VerifyResult {
  valid: boolean;
  corruptedAt?: number;
  total: number;
  committed: number;
  rolledBack: number;
  corrections: number;
  flags: number;
  protocol?: string;
  version?: string;
  protocolMismatch: boolean;
  versionMismatch: boolean;
  expectedProtocol: string;
  expectedVersion: string;
}

export function parseLedger(text: string): ExportedLedger {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (err) {
    throw new Error(`Could not parse JSON: ${(err as Error).message}`);
  }
  if (!parsed || typeof parsed !== "object" || !("entries" in parsed)) {
    throw new Error(
      "Ledger JSON must be an object with an 'entries' array. Use map.exportLedger() from @model-action-protocol/core to produce one."
    );
  }
  const ledger = parsed as ExportedLedger;
  if (!Array.isArray(ledger.entries)) {
    throw new Error("Ledger 'entries' must be an array.");
  }
  return ledger;
}

export function verifyLedger(ledger: ExportedLedger): VerifyResult {
  const result = verifyChain(
    ledger.entries.map((e) => ({
      sequence: e.sequence,
      action: e.action,
      stateBefore: e.stateBefore,
      stateAfter: e.stateAfter,
      parentHash: e.parentHash,
      hash: e.hash,
      critic: e.critic,
    }))
  );

  const stats = ledger.stats ?? computeStats(ledger.entries);

  return {
    valid: result.valid,
    corruptedAt: result.corruptedAt,
    total: stats.total,
    committed: stats.committed,
    rolledBack: stats.rolledBack,
    corrections: stats.corrections,
    flags: stats.flags,
    protocol: ledger.protocol,
    version: ledger.version,
    protocolMismatch:
      ledger.protocol !== undefined && ledger.protocol !== MAP_PROTOCOL,
    versionMismatch:
      ledger.version !== undefined && ledger.version !== MAP_VERSION,
    expectedProtocol: MAP_PROTOCOL,
    expectedVersion: MAP_VERSION,
  };
}

function computeStats(entries: LedgerEntry[]) {
  const committed = entries.filter(
    (e) => e.status === "ACTIVE" && e.action?.tool !== "ROLLBACK"
  ).length;
  const rolledBack = entries.filter(
    (e) => e.status === "ROLLED_BACK"
  ).length;
  const corrections = entries.filter(
    (e) => e.critic?.verdict === "CORRECTED"
  ).length;
  const flags = entries.filter(
    (e) => e.critic?.verdict === "FLAGGED"
  ).length;
  return { total: entries.length, committed, rolledBack, corrections, flags };
}
