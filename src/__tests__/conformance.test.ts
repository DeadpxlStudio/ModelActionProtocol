// =============================================================================
// Conformance tests — TS side
//
// Loads the frozen v0.1 fixtures from spec/fixtures/v0.1/ and verifies them.
// These same fixtures are loaded by the Python SDK's conformance tests; both
// implementations must accept every fixture as valid and detect every
// mutation at the correct index.
//
// If a future spec version requires new fixtures, add a new directory
// (spec/fixtures/v0.2/) and a new test block. Existing fixtures are immutable.
// =============================================================================

import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { createHash } from "node:crypto";
import { verifyChain, sha256, computeEntryHash, serializeState } from "../snapshot.js";
import { LearningEngine } from "../learning.js";
import type { LedgerEntry } from "../protocol.js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const FIXTURES_V01 = join(__dirname, "..", "..", "spec", "fixtures", "v0.1");

interface Fixture {
  protocol: string;
  version: string;
  entries: LedgerEntry[];
  stats: Record<string, number>;
  expectedPatterns?: Array<{ tool: string; fingerprint: string; count: number }>;
}

function loadFixture(name: string): Fixture {
  return JSON.parse(readFileSync(join(FIXTURES_V01, name), "utf8"));
}

// ─── Spec §6.4 worked example — pin the hash ────────────────────────────────
// These literal hashes are copied from `spec/SPEC.md` §6.4. The Python test
// `test_canonical_json_known_hash` asserts the identical literals. If either
// side changes, both must change — they are coupled by design.

describe("spec §6.4 worked example", () => {
  it("produces the documented entry hash", () => {
    const stateHash = sha256(serializeState(null));
    // SPEC.md §6.4: state used = null → SHA-256(JCS(null)) = SHA-256("null")
    expect(stateHash).toBe(
      "74234e98afe7498fb5daf1f36ac2d78acc339464f950703b8c019892f982b90b"
    );

    const entryHash = computeEntryHash(
      0,
      { tool: "ping", input: {}, output: "pong" },
      stateHash,
      stateHash,
      "0".repeat(64),
      { verdict: "PASS", reason: "ok" }
    );
    // SPEC.md §6.4: documented entry hash for the worked example.
    expect(entryHash).toBe(
      "25d29bc25a183ebdb29b70b6a03ed2ad8d31033d1fb6347f656b21d7e9efb650"
    );
  });
});

// ─── Per-fixture verification ───────────────────────────────────────────────

const ledgerFixtures = [
  "pass-only-3-actions.json",
  "corrected-mid-chain.json",
  "flagged-halt.json",
  "rollback-and-resume.json",
  "learning-patterns.json",
  "edge-cases.json",
];

describe.each(ledgerFixtures)("fixture %s", (name) => {
  const fixture = loadFixture(name);

  it("declares MAP protocol and matching version", () => {
    expect(fixture.protocol).toBe("map");
    expect(fixture.version).toBe("0.1.0");
  });

  it("verifies as a valid chain", () => {
    expect(verifyChain(fixture.entries)).toEqual({ valid: true });
  });

  it("recomputes each entry's hash to the stored value", () => {
    for (const e of fixture.entries) {
      const expected = computeEntryHash(
        e.sequence,
        e.action,
        e.stateBefore,
        e.stateAfter,
        e.parentHash,
        e.critic
      );
      expect(e.hash).toBe(expected);
    }
  });

  it("recomputes each state hash from the embedded snapshot", () => {
    for (const e of fixture.entries) {
      expect(e.stateBefore).toBe(sha256(serializeState(e.snapshots.before)));
      expect(e.stateAfter).toBe(sha256(serializeState(e.snapshots.after)));
    }
  });
});

// ─── Negative tests — mutation detection ────────────────────────────────────

describe("mutation detection", () => {
  it.each(ledgerFixtures)(
    "detects mutation of entry hash at correct index — %s",
    (name) => {
      const fixture = loadFixture(name);
      if (fixture.entries.length === 0) return;

      const targetIdx = Math.min(1, fixture.entries.length - 1);
      const mutated = fixture.entries.map((e, i) =>
        i === targetIdx ? { ...e, hash: "f".repeat(64) } : e
      );
      const result = verifyChain(mutated);
      expect(result.valid).toBe(false);
      // Hash-integrity check at the target fires before chain linkage at the
      // next index, so corruption is always reported at the target.
      expect(result.corruptedAt).toBe(targetIdx);
    }
  );

  it.each(ledgerFixtures)(
    "detects mutation of action at correct index — %s",
    (name) => {
      const fixture = loadFixture(name);
      if (fixture.entries.length === 0) return;

      const targetIdx = 0;
      const mutated = fixture.entries.map((e, i) =>
        i === targetIdx
          ? { ...e, action: { ...e.action, tool: "tampered" } }
          : e
      );
      const result = verifyChain(mutated);
      expect(result.valid).toBe(false);
      expect(result.corruptedAt).toBe(targetIdx);
    }
  );

  it.each(ledgerFixtures)(
    "detects mutation of critic verdict at correct index — %s",
    (name) => {
      const fixture = loadFixture(name);
      if (fixture.entries.length === 0) return;

      const targetIdx = 0;
      const mutated = fixture.entries.map((e, i) =>
        i === targetIdx
          ? { ...e, critic: { ...e.critic, verdict: "PASS" as const } }
          : e
      );
      // Skip if the target is already PASS — mutation would be a no-op.
      if (fixture.entries[targetIdx].critic.verdict === "PASS") return;
      const result = verifyChain(mutated);
      expect(result.valid).toBe(false);
      expect(result.corruptedAt).toBe(targetIdx);
    }
  );

  it("detects bad genesis parentHash", () => {
    const fixture = loadFixture("pass-only-3-actions.json");
    const mutated = fixture.entries.map((e, i) =>
      i === 0 ? { ...e, parentHash: "1".repeat(64) } : e
    );
    const result = verifyChain(mutated);
    expect(result.valid).toBe(false);
    expect(result.corruptedAt).toBe(0);
  });

  it("detects sequence gap", () => {
    const fixture = loadFixture("pass-only-3-actions.json");
    const mutated = fixture.entries.map((e, i) =>
      i === 1 ? { ...e, sequence: 99 } : e
    );
    const result = verifyChain(mutated);
    expect(result.valid).toBe(false);
    expect(result.corruptedAt).toBe(1);
  });

  // ─── Structural tampering — order, insertion, deletion ──────────────────

  it("detects entry swap", () => {
    // Swap entries[0] and entries[1] → sequence continuity fails immediately.
    const fixture = loadFixture("pass-only-3-actions.json");
    const swapped = [...fixture.entries];
    [swapped[0], swapped[1]] = [swapped[1], swapped[0]];
    const result = verifyChain(swapped);
    expect(result.valid).toBe(false);
    expect(result.corruptedAt).toBe(0);
  });

  it("detects entry insertion (synthesized middle entry)", () => {
    // Inject a fabricated entry between index 0 and 1. Even if its sequence
    // is set to 1, the chain linkage at index 2 (now original entry 1)
    // breaks because parentHash points to the original entry-0 hash, not the
    // injected entry's hash.
    const fixture = loadFixture("pass-only-3-actions.json");
    const fakeEntry = {
      ...fixture.entries[0],
      id: "11111111-1111-4111-8111-111111111111",
      sequence: 1,
      action: { tool: "injected", input: {}, output: null },
      hash: "f".repeat(64),
    };
    const tampered = [
      fixture.entries[0],
      fakeEntry,
      ...fixture.entries.slice(1).map((e, i) => ({ ...e, sequence: i + 2 })),
    ];
    const result = verifyChain(tampered);
    expect(result.valid).toBe(false);
    // The injected entry's stored hash is bogus, so hash integrity fails at index 1.
    expect(result.corruptedAt).toBe(1);
  });

  it("detects entry deletion", () => {
    // Remove entries[1]. Index 1 now holds the original entry 2 with
    // sequence=2, so sequence continuity (sequence !== i) fails at index 1.
    const fixture = loadFixture("pass-only-3-actions.json");
    const truncated = [fixture.entries[0], ...fixture.entries.slice(2)];
    const result = verifyChain(truncated);
    expect(result.valid).toBe(false);
    expect(result.corruptedAt).toBe(1);
  });
});

// ─── LearningEngine fingerprint conformance ─────────────────────────────────

describe("learning-patterns fingerprint conformance", () => {
  const fixture = loadFixture("learning-patterns.json");

  it("includes expectedPatterns in the fixture", () => {
    expect(fixture.expectedPatterns).toBeDefined();
    expect(fixture.expectedPatterns!.length).toBeGreaterThan(0);
  });

  it("reproduces every expected fingerprint from the ledger", () => {
    const engine = new LearningEngine();
    const patterns = engine.analyzePatterns(fixture.entries);
    const observed = patterns
      .map((p) => ({ tool: p.tool, fingerprint: p.fingerprint, count: p.count }))
      .sort((a, b) => a.fingerprint.localeCompare(b.fingerprint));
    const expected = [...fixture.expectedPatterns!].sort((a, b) =>
      a.fingerprint.localeCompare(b.fingerprint)
    );
    expect(observed).toEqual(expected);
  });

  it("each expected fingerprint matches the documented formula", () => {
    // Formula: SHA-256(verdict + ":" + tool + ":" + (correctionTool ?? "none"))
    for (const expected of fixture.expectedPatterns!) {
      // Find a matching entry to derive the inputs
      const e = fixture.entries.find(
        (entry) =>
          entry.action.tool === expected.tool &&
          (entry.critic.verdict === "CORRECTED" ||
            entry.critic.verdict === "FLAGGED")
      );
      if (!e) continue;
      const correctionTool = e.critic.correction?.tool ?? "none";
      const input = `${e.critic.verdict}:${e.action.tool}:${correctionTool}`;
      const computed = createHash("sha256").update(input).digest("hex");
      expect(expected.fingerprint).toBe(computed);
    }
  });
});

// ─── Unicode normalization sensitivity ──────────────────────────────────────
// Spec mandates JCS, which assumes input strings are NFC-normalized.
// A caller passing NFD will produce a different hash than a caller passing
// NFC for the "same" string. This test pins that behavior so users know
// canonicalization does not silently normalize.

describe("unicode normalization sensitivity", () => {
  it("NFC and NFD strings produce different state hashes", () => {
    const nfc = "café"; // single code point U+00E9
    const nfd = "café"; // U+0065 U+0301
    expect(nfc).not.toBe(nfd);
    expect(nfc.normalize("NFC")).toBe(nfd.normalize("NFC"));
    const hashNfc = sha256(serializeState({ name: nfc }));
    const hashNfd = sha256(serializeState({ name: nfd }));
    expect(hashNfc).not.toBe(hashNfd);
  });
});

// ─── Fixture discovery ──────────────────────────────────────────────────────

describe("fixture directory", () => {
  it("contains exactly the documented v0.1 fixtures", () => {
    const found = readdirSync(FIXTURES_V01)
      .filter((f) => f.endsWith(".json"))
      .sort();
    const expected = [
      "corrected-mid-chain.json",
      "edge-cases.json",
      "flagged-halt.json",
      "learning-patterns.json",
      "pass-only-3-actions.json",
      "rollback-and-resume.json",
    ];
    expect(found).toEqual(expected);
  });
});
