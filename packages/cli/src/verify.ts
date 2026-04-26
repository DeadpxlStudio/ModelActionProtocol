import { readFileSync } from "node:fs";
import { verifyChain, MAP_VERSION, MAP_PROTOCOL } from "@model-action-protocol/core";
import type { LedgerEntry } from "@model-action-protocol/core";
import { color, dim, bold, green, red, yellow } from "./tty.js";

interface ExportedLedger {
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
  protocolMismatch?: boolean;
  versionMismatch?: boolean;
}

export interface VerifyOptions {
  json?: boolean;
  source?: string;
}

export async function readLedgerInput(input: string): Promise<ExportedLedger> {
  const raw = input === "-" ? await readStdin() : readFileSync(input, "utf-8");
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    throw new Error(`Could not parse ledger as JSON: ${(err as Error).message}`);
  }
  if (!parsed || typeof parsed !== "object" || !("entries" in parsed)) {
    throw new Error("Ledger JSON must be an object with an 'entries' array (use map.exportLedger() to produce one)");
  }
  const ledger = parsed as ExportedLedger;
  if (!Array.isArray(ledger.entries)) {
    throw new Error("Ledger 'entries' must be an array");
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
    protocolMismatch: ledger.protocol !== undefined && ledger.protocol !== MAP_PROTOCOL,
    versionMismatch: ledger.version !== undefined && ledger.version !== MAP_VERSION,
  };
}

export async function runVerify(input: string, options: VerifyOptions = {}): Promise<number> {
  let ledger: ExportedLedger;
  try {
    ledger = await readLedgerInput(input);
  } catch (err) {
    if (options.json) {
      process.stdout.write(JSON.stringify({ valid: false, error: (err as Error).message }) + "\n");
    } else {
      process.stderr.write(`${red("✗")} ${(err as Error).message}\n`);
    }
    return 2;
  }

  const result = verifyLedger(ledger);

  if (options.json) {
    process.stdout.write(JSON.stringify(result) + "\n");
    return result.valid ? 0 : 1;
  }

  printHumanReport(result, ledger, options.source ?? input);
  return result.valid ? 0 : 1;
}

function printHumanReport(result: VerifyResult, ledger: ExportedLedger, source: string) {
  const lines: string[] = [];
  lines.push("");
  if (result.valid) {
    lines.push(`  ${bold(green("✓ Verified"))}  ${dim(source)}`);
  } else {
    lines.push(`  ${bold(red("✗ Tampered"))}  ${dim(source)}`);
  }
  lines.push("");
  lines.push(`  ${dim("protocol")}        ${result.protocol ?? dim("(not declared)")}${
    result.protocolMismatch ? "  " + yellow("(mismatch)") : ""
  }`);
  lines.push(`  ${dim("version")}         ${result.version ?? dim("(not declared)")}${
    result.versionMismatch ? "  " + yellow(`(this CLI is ${MAP_VERSION})`) : ""
  }`);
  lines.push(`  ${dim("entries")}         ${result.total}`);
  lines.push(`  ${dim("committed")}       ${result.committed}`);
  lines.push(`  ${dim("rolled back")}     ${result.rolledBack}`);
  lines.push(`  ${dim("corrections")}     ${result.corrections}`);
  lines.push(`  ${dim("flags")}           ${result.flags}`);

  if (!result.valid && result.corruptedAt !== undefined) {
    const entry = ledger.entries[result.corruptedAt];
    lines.push("");
    lines.push(`  ${bold(red("Tamper detected at entry"))} #${result.corruptedAt}`);
    if (entry) {
      lines.push(`    ${dim("tool")}     ${entry.action?.tool ?? dim("(unknown)")}`);
      lines.push(`    ${dim("seq")}      ${entry.sequence}`);
      lines.push(`    ${dim("hash")}     ${entry.hash?.slice(0, 16)}…`);
    }
    lines.push("");
    lines.push(`  ${dim("The chain is broken at this point. Every entry after this is suspect.")}`);
  }

  lines.push("");
  process.stdout.write(lines.join("\n") + "\n");
}

function computeStats(entries: LedgerEntry[]) {
  const committed = entries.filter((e) => e.status === "ACTIVE" && e.action?.tool !== "ROLLBACK").length;
  const rolledBack = entries.filter((e) => e.status === "ROLLED_BACK").length;
  const corrections = entries.filter((e) => e.critic?.verdict === "CORRECTED").length;
  const flags = entries.filter((e) => e.critic?.verdict === "FLAGGED").length;
  return { total: entries.length, committed, rolledBack, corrections, flags };
}

async function readStdin(): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
  }
  return Buffer.concat(chunks).toString("utf-8");
}

// touch: keep `color` import used in case future flags need it
void color;
