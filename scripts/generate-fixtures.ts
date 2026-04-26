// =============================================================================
// Conformance fixture generator
//
// Produces the v0.1 fixtures that both TS and Python conformance tests load.
// Run once at v0.1 freeze. Output is committed to git and never regenerated.
//
//   npx tsx scripts/generate-fixtures.ts
//
// Determinism: UUIDs and timestamps are pinned via seeded generators so the
// generator's output can be regenerated bit-for-bit if a future fix requires
// it. To re-pin (e.g., for v0.2), edit the SEED constant.
// =============================================================================

import { writeFileSync, mkdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import {
  captureSnapshot,
  computeEntryHash,
  serializeState,
} from "../src/snapshot.js";
import { LearningEngine } from "../src/learning.js";
import { MAP_PROTOCOL, MAP_VERSION } from "../src/protocol.js";
import type {
  LedgerEntry,
  ActionRecord,
  CriticResult,
  LedgerEntryStatus,
} from "../src/protocol.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = join(__dirname, "..", "spec", "fixtures", "v0.1");
const SEED = "map-v0.1-fixtures";
const FIXED_TIMESTAMP = "2026-04-25T00:00:00.000Z";

// Deterministic UUID generator: seed + counter → SHA-256 → format as UUID v4-ish.
let uuidCounter = 0;
function detUuid(): string {
  const h = createHash("sha256").update(`${SEED}:${uuidCounter++}`).digest("hex");
  return [
    h.slice(0, 8),
    h.slice(8, 12),
    "4" + h.slice(13, 16),
    "8" + h.slice(17, 20),
    h.slice(20, 32),
  ].join("-");
}

function buildEntry(
  prev: LedgerEntry | null,
  action: ActionRecord,
  stateBefore: unknown,
  stateAfter: unknown,
  critic: CriticResult,
  status: LedgerEntryStatus = "ACTIVE"
): LedgerEntry {
  const sequence = prev ? prev.sequence + 1 : 0;
  const parentHash = prev ? prev.hash : "0".repeat(64);
  const before = captureSnapshot(stateBefore);
  const after = captureSnapshot(stateAfter);
  const hash = computeEntryHash(
    sequence,
    action,
    before.hash,
    after.hash,
    parentHash,
    critic
  );
  return {
    id: detUuid(),
    sequence,
    timestamp: FIXED_TIMESTAMP,
    action,
    stateBefore: before.hash,
    stateAfter: after.hash,
    snapshots: { before: before.serialized, after: after.serialized },
    parentHash,
    hash,
    critic,
    status,
  };
}

function getStats(entries: LedgerEntry[]) {
  return {
    total: entries.length,
    committed: entries.filter(
      (e) => e.status === "ACTIVE" && e.action.tool !== "ROLLBACK"
    ).length,
    rolledBack: entries.filter((e) => e.status === "ROLLED_BACK").length,
    corrections: entries.filter((e) => e.critic.verdict === "CORRECTED").length,
    flags: entries.filter((e) => e.critic.verdict === "FLAGGED").length,
  };
}

function writeFixture(filename: string, entries: LedgerEntry[]): void {
  const fixture = {
    protocol: MAP_PROTOCOL,
    version: MAP_VERSION,
    entries,
    stats: getStats(entries),
  };
  const path = join(FIXTURES_DIR, filename);
  writeFileSync(path, JSON.stringify(fixture, null, 2) + "\n", "utf8");
  console.log(`  wrote ${filename} (${entries.length} entries)`);
}

mkdirSync(FIXTURES_DIR, { recursive: true });
console.log(`generating fixtures at ${FIXTURES_DIR}`);

// ─── Fixture 1: pass-only-3-actions ─────────────────────────────────────────
{
  uuidCounter = 0;
  let prev: LedgerEntry | null = null;
  const entries: LedgerEntry[] = [];

  let state: Record<string, unknown> = { counter: 0 };

  for (const v of [1, 2, 3]) {
    const next = { counter: v };
    const e = buildEntry(
      prev,
      { tool: "increment", input: { by: 1 }, output: { ok: true } },
      state,
      next,
      { verdict: "PASS", reason: "counter increment is well-formed" }
    );
    entries.push(e);
    prev = e;
    state = next;
  }

  writeFixture("pass-only-3-actions.json", entries);
}

// ─── Fixture 2: corrected-mid-chain ─────────────────────────────────────────
{
  uuidCounter = 100;
  let prev: LedgerEntry | null = null;
  const entries: LedgerEntry[] = [];

  // Action 1 — PASS
  let s0: Record<string, unknown> = { balance: 100 };
  let s1: Record<string, unknown> = { balance: 90 };
  prev = buildEntry(
    prev,
    { tool: "debit", input: { amount: 10 }, output: { ok: true } },
    s0,
    s1,
    { verdict: "PASS", reason: "debit within available balance" }
  );
  entries.push(prev);

  // Action 2 — CORRECTED (would have over-debited; critic auto-fixes)
  let s2: Record<string, unknown> = { balance: 85 };
  prev = buildEntry(
    prev,
    { tool: "debit", input: { amount: 5 }, output: { ok: true } },
    s1,
    s2,
    {
      verdict: "CORRECTED",
      reason: "original debit of 50 exceeded balance; corrected to 5",
      correction: { tool: "debit", input: { amount: 5 } },
    }
  );
  entries.push(prev);

  // Action 3 — PASS
  let s3: Record<string, unknown> = { balance: 80 };
  prev = buildEntry(
    prev,
    { tool: "debit", input: { amount: 5 }, output: { ok: true } },
    s2,
    s3,
    { verdict: "PASS", reason: "ok" }
  );
  entries.push(prev);

  writeFixture("corrected-mid-chain.json", entries);
}

// ─── Fixture 3: flagged-halt ────────────────────────────────────────────────
{
  uuidCounter = 200;
  let prev: LedgerEntry | null = null;
  const entries: LedgerEntry[] = [];

  let s0: Record<string, unknown> = { account: { id: "A1", status: "open" } };
  let s1: Record<string, unknown> = {
    account: { id: "A1", status: "open" },
    transactions: [{ amount: 500 }],
  };
  prev = buildEntry(
    prev,
    {
      tool: "logTransaction",
      input: { amount: 500 },
      output: { logged: true },
    },
    s0,
    s1,
    { verdict: "PASS", reason: "transaction within normal range" }
  );
  entries.push(prev);

  // Action 2 — FLAGGED, halts execution. State unchanged because action did not commit.
  prev = buildEntry(
    prev,
    {
      tool: "wireTransfer",
      input: { amount: 100000, to: "external" },
      output: null,
      reversalStrategy: "ESCALATE",
    },
    s1,
    s1,
    {
      verdict: "FLAGGED",
      reason: "wire transfer over $50k requires human approval",
    }
  );
  entries.push(prev);

  writeFixture("flagged-halt.json", entries);
}

// ─── Fixture 4: rollback-and-resume ─────────────────────────────────────────
{
  uuidCounter = 300;
  let prev: LedgerEntry | null = null;
  const entries: LedgerEntry[] = [];

  // Entry 0 — ACTIVE
  let s0: Record<string, unknown> = { items: [] };
  let s1: Record<string, unknown> = { items: [{ id: 1 }] };
  prev = buildEntry(
    prev,
    { tool: "addItem", input: { id: 1 }, output: { ok: true } },
    s0,
    s1,
    { verdict: "PASS", reason: "ok" }
  );
  entries.push(prev);

  // Entry 1 — ROLLED_BACK (was a mistake, undone)
  let s2: Record<string, unknown> = { items: [{ id: 1 }, { id: 2 }] };
  prev = buildEntry(
    prev,
    { tool: "addItem", input: { id: 2 }, output: { ok: true } },
    s1,
    s2,
    { verdict: "PASS", reason: "ok" },
    "ROLLED_BACK"
  );
  entries.push(prev);

  // Entry 2 — the rollback action itself, ACTIVE; state restored to s1
  prev = buildEntry(
    prev,
    {
      tool: "ROLLBACK",
      input: { targetId: entries[0].id },
      output: { entriesReverted: 1 },
    },
    s2,
    s1,
    { verdict: "PASS", reason: "rollback restoring state to entry 0" }
  );
  entries.push(prev);

  // Entry 3 — fresh action after rollback, ACTIVE
  let s4: Record<string, unknown> = { items: [{ id: 1 }, { id: 3 }] };
  prev = buildEntry(
    prev,
    { tool: "addItem", input: { id: 3 }, output: { ok: true } },
    s1,
    s4,
    { verdict: "PASS", reason: "ok" }
  );
  entries.push(prev);

  writeFixture("rollback-and-resume.json", entries);
}

// ─── Fixture 5: learning-patterns ───────────────────────────────────────────
// A ledger with three repeated CORRECTED-on-same-tool patterns plus expected
// fingerprints for LearningEngine conformance.
{
  uuidCounter = 400;
  let prev: LedgerEntry | null = null;
  const entries: LedgerEntry[] = [];

  for (let i = 0; i < 4; i++) {
    let sBefore: Record<string, unknown> = { tickets: i };
    let sAfter: Record<string, unknown> = { tickets: i + 1 };
    prev = buildEntry(
      prev,
      {
        tool: "createTicket",
        input: { title: `Issue ${i}` },
        output: { id: `T-${i}` },
      },
      sBefore,
      sAfter,
      {
        verdict: "CORRECTED",
        reason: "ticket title missing project tag; auto-prefixed",
        correction: {
          tool: "createTicket",
          input: { title: `[OPS] Issue ${i}` },
        },
      }
    );
    entries.push(prev);
  }

  // Two FLAGGED on a different tool (no correction target → "none")
  for (let i = 0; i < 2; i++) {
    let sBefore: Record<string, unknown> = { holds: i };
    prev = buildEntry(
      prev,
      {
        tool: "closeAccount",
        input: { accountId: `A-${i}` },
        output: null,
        reversalStrategy: "ESCALATE",
      },
      sBefore,
      sBefore,
      {
        verdict: "FLAGGED",
        reason: "account has regulatory hold; closure requires approval",
      }
    );
    entries.push(prev);
  }

  // Use LearningEngine to compute expected patterns
  const engine = new LearningEngine();
  const patterns = engine.analyzePatterns(entries);

  // Fingerprint formula: SHA-256(verdict + ":" + tool + ":" + (correctionTool ?? "none"))
  const expectedFingerprints = patterns
    .map((p) => ({
      tool: p.tool,
      fingerprint: p.fingerprint,
      count: p.count,
    }))
    .sort((a, b) => a.fingerprint.localeCompare(b.fingerprint));

  const fixture = {
    protocol: MAP_PROTOCOL,
    version: MAP_VERSION,
    entries,
    stats: getStats(entries),
    expectedPatterns: expectedFingerprints,
  };
  const path = join(FIXTURES_DIR, "learning-patterns.json");
  writeFileSync(path, JSON.stringify(fixture, null, 2) + "\n", "utf8");
  console.log(
    `  wrote learning-patterns.json (${entries.length} entries, ${expectedFingerprints.length} patterns)`
  );
}

// ─── Fixture 6: edge-cases ──────────────────────────────────────────────────
// Covers the JCS-sensitive corners: unicode (NFC vs NFD must converge),
// deeply-nested objects, empty payload, large payload. Without these the
// "Python verifies TS fixtures" test passes vacuously on toy data and lets
// a real NFC-vs-NFD divergence ship to prod.
{
  uuidCounter = 500;
  let prev: LedgerEntry | null = null;
  const entries: LedgerEntry[] = [];

  // Edge 1: Unicode — café (NFC pre-composed: U+00E9) in input + state.
  // Spec mandates JCS-canonical input, so callers passing NFD will produce
  // a different hash than callers passing NFC. We test the NFC path here;
  // the unit-test side asserts that deliberate NFD strings produce a
  // different hash (so users can't accidentally rely on normalization).
  prev = buildEntry(
    prev,
    {
      tool: "logCustomer",
      input: { name: "café", emoji: "🥐", chinese: "你好" },
      output: { ok: true },
    },
    { customers: [] },
    { customers: [{ name: "café" }] },
    { verdict: "PASS", reason: "unicode preserved through canonicalization" }
  );
  entries.push(prev);

  // Edge 2: Empty input/output/state.
  prev = buildEntry(
    prev,
    { tool: "noop", input: {}, output: {} },
    { customers: [{ name: "café" }] },
    { customers: [{ name: "café" }] },
    { verdict: "PASS", reason: "no-op" }
  );
  entries.push(prev);

  // Edge 3: Deep nesting — 6 levels deep.
  const deepBefore: Record<string, unknown> = {
    a: { b: { c: { d: { e: { f: { value: 0 } } } } } },
  };
  const deepAfter: Record<string, unknown> = {
    a: { b: { c: { d: { e: { f: { value: 1 } } } } } },
  };
  prev = buildEntry(
    prev,
    {
      tool: "deepUpdate",
      input: { path: "a.b.c.d.e.f.value", to: 1 },
      output: { ok: true },
    },
    deepBefore,
    deepAfter,
    { verdict: "PASS", reason: "deep nesting preserved" }
  );
  entries.push(prev);

  // Edge 4: Large payload — ~10KB serialized via 200 small items.
  const items: Array<Record<string, unknown>> = [];
  for (let i = 0; i < 200; i++) {
    items.push({
      id: `item-${i.toString().padStart(4, "0")}`,
      label: `Description for item ${i}`,
      tags: ["alpha", "beta", "gamma"],
      score: i * 0.5,
    });
  }
  prev = buildEntry(
    prev,
    {
      tool: "bulkImport",
      input: { count: items.length },
      output: { imported: items.length },
    },
    { items: [] },
    { items },
    { verdict: "PASS", reason: "bulk import of 200 items" }
  );
  entries.push(prev);

  writeFixture("edge-cases.json", entries);
}

// ─── Spec §6.4 worked example ───────────────────────────────────────────────
// Print the canonical bytes and SHA-256 for the spec's worked example so we
// can paste real values into spec/SPEC.md.
{
  const action = { tool: "ping", input: {}, output: "pong" };
  const stateHash = createHash("sha256")
    .update(serializeState(null))
    .digest("hex");
  const critic = { verdict: "PASS" as const, reason: "ok" };
  const payload = {
    sequence: 0,
    action,
    stateBefore: stateHash,
    stateAfter: stateHash,
    parentHash: "0".repeat(64),
    critic,
  };
  const canonical = serializeState(payload);
  const hash = createHash("sha256").update(canonical).digest("hex");
  console.log("\nSpec §6.4 worked example:");
  console.log(`  state used: null  →  stateBefore = stateAfter = ${stateHash}`);
  console.log(`  canonical payload bytes:\n    ${canonical}`);
  console.log(`  expected entry hash: ${hash}`);
}

console.log("\nfixture generation complete.");
