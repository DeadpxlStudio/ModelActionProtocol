#!/usr/bin/env node
// Generates two refund-flow demo ledgers for the verifier's "try a sample"
// buttons. Output lands in apps/verifier/public/ so it's served as static
// content. These are NOT the canonical conformance fixtures — those live
// at spec/fixtures/v0.1/ and are immutable. These are narrative demos.
//
//   sample-valid.ledger.json     — a clean refund-flow ledger
//   sample-tampered.ledger.json  — same ledger with action.output mutated
//
// Used by:
//   • Verifier web app "try a sample" / "try a tampered one" buttons
//   • Distribution tweets / DMs (?url= deep links to GitHub raw content)
//
// Re-run after any change to core's canonicalization or Ledger.append shape.

import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Ledger } from "../dist/ledger.js";

const here = dirname(fileURLToPath(import.meta.url));
const outDir = resolve(here, "..", "apps", "verifier", "public");
mkdirSync(outDir, { recursive: true });

// --- A small, plausible scenario: refund-flow agent ----------------------
const ledger = new Ledger();

let state = {
  customer: { id: "cust_42", name: "Aanya Iyer", email: "a@iyer.co" },
  charges: [
    { id: "ch_001", amount: 4900, status: "succeeded", created: "2026-04-19" },
  ],
  refunds: [],
};

const next = (mutator) => {
  const before = structuredClone(state);
  mutator();
  return { before, after: structuredClone(state) };
};

// 1. Read customer (PASS)
{
  const { before, after } = next(() => {});
  await ledger.append(
    {
      tool: "getCustomer",
      input: { id: "cust_42" },
      output: state.customer,
      reversalStrategy: undefined,
    },
    before,
    after,
    { verdict: "PASS", reason: "Read action — no state change." }
  );
}

// 2. Issue refund (PASS, COMPENSATE)
{
  const { before, after } = next(() => {
    state.refunds.push({
      id: "re_001",
      charge: "ch_001",
      amount: 4900,
      created: "2026-04-26",
      reason: "requested_by_customer",
    });
  });
  await ledger.append(
    {
      tool: "issueRefund",
      input: { chargeId: "ch_001", amount: 4900, reason: "requested_by_customer" },
      output: { id: "re_001", status: "succeeded" },
      reversalStrategy: "COMPENSATE",
    },
    before,
    after,
    {
      verdict: "PASS",
      reason: "Refund matches a real charge and is within the customer's eligible window.",
    }
  );
}

// 3. Critic CORRECTED — agent tried to email customer with a typo'd template
{
  const { before, after } = next(() => {
    // (no state mutation — email send is external; we record the intent + correction)
  });
  await ledger.append(
    {
      tool: "sendEmail",
      input: {
        to: "a@iyer.co",
        subject: "Your refund of $49 has been issued",
        body: "Hi Aanya, your refund of $49 has been issued and will reach your card in 3-5 business days.",
      },
      output: { messageId: "msg_77f", queued: true },
      reversalStrategy: "ESCALATE",
    },
    before,
    after,
    {
      verdict: "CORRECTED",
      reason: "Original draft addressed customer by wrong name (Anya, not Aanya). Critic regenerated the body with the correct name.",
      correction: {
        tool: "sendEmail",
        input: {
          to: "a@iyer.co",
          subject: "Your refund of $49 has been issued",
          body: "Hi Aanya, your refund of $49 has been issued and will reach your card in 3-5 business days.",
        },
      },
    }
  );
}

// 4. FLAGGED — agent tried to issue a second, duplicate refund
{
  const { before, after } = next(() => {
    // No state mutation — the FLAGGED action was held before commit
  });
  await ledger.append(
    {
      tool: "issueRefund",
      input: { chargeId: "ch_001", amount: 4900, reason: "requested_by_customer" },
      output: { halted: true, reason: "duplicate_refund_detected" },
      reversalStrategy: "COMPENSATE",
    },
    before,
    after,
    {
      verdict: "FLAGGED",
      reason: "ch_001 has already been refunded in full (re_001). A second refund would exceed the original charge.",
    }
  );
}

const exported = ledger.export();
const validPath = resolve(outDir, "sample-valid.ledger.json");
writeFileSync(validPath, JSON.stringify(exported, null, 2));

// --- Tamper one entry's output to break the chain ------------------------
const tampered = JSON.parse(JSON.stringify(exported));
// Mutate entry 1's output field — the recorded hash will no longer match the
// recomputed hash, and entry 2's parentHash will no longer match entry 1's
// hash. The verifier should pin the break at index 1.
tampered.entries[1].action.output = { id: "re_001", status: "succeeded", amount: 99999 };

const tamperedPath = resolve(outDir, "sample-tampered.ledger.json");
writeFileSync(tamperedPath, JSON.stringify(tampered, null, 2));

console.log(`✓ wrote ${validPath}`);
console.log(`✓ wrote ${tamperedPath}`);
console.log(`  ${exported.entries.length} entries, ${exported.stats.corrections} corrections, ${exported.stats.flags} flags`);
