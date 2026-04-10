import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { Ledger } from "../ledger.js";
import { SQLiteLedgerStore } from "../adapters/sqlite.js";
import { randomUUID } from "crypto";
import { existsSync, unlinkSync } from "fs";

describe("SQLite Persistence", () => {
  const DB_PATH = "test_persistence.db";

  beforeEach(() => {
    if (existsSync(DB_PATH)) {
      unlinkSync(DB_PATH);
    }
  });

  afterEach(() => {
    if (existsSync(DB_PATH)) {
      unlinkSync(DB_PATH);
    }
  });

  it("should persist entries across restarts", () => {
    const store = new SQLiteLedgerStore(DB_PATH);
    const ledger = new Ledger({ store });

    // 1. Add some entries
    ledger.append(
      { tool: "testTool", input: { item: "A" }, output: { success: true } },
      { count: 0 },
      { count: 1 },
      { verdict: "PASS", reason: "All good" }
    );

    ledger.append(
      { tool: "testTool", input: { item: "B" }, output: { success: true } },
      { count: 1 },
      { count: 2 },
      { verdict: "PASS", reason: "All good" }
    );

    expect(ledger.getEntries().length).toBe(2);
    
    // Close store
    store.close();

    // 2. Restart ledger with the same database
    const store2 = new SQLiteLedgerStore(DB_PATH);
    const ledger2 = new Ledger({ store: store2 });

    const entries = ledger2.getEntries();
    expect(entries.length).toBe(2);
    expect(entries[0].action.tool).toBe("testTool");
    expect((entries[0].action.input as any).item).toBe("A");
    expect((entries[1].action.input as any).item).toBe("B");

    store2.close();
  });

  it("should persist rollback status across restarts", () => {
    const store = new SQLiteLedgerStore(DB_PATH);
    const ledger = new Ledger({ store });

    const entry1 = ledger.append(
      { tool: "testTool", input: { v: 1 }, output: { ok: true } },
      {}, {}, { verdict: "PASS", reason: "X" }
    );

    ledger.append(
      { tool: "testTool", input: { v: 2 }, output: { ok: true } },
      {}, {}, { verdict: "PASS", reason: "X" }
    );

    // Rollback to entry 1
    ledger.rollbackTo(entry1.id);

    expect(ledger.getEntries().length).toBe(3); // 2 actions + 1 rollback entry
    expect(ledger.getEntry(entry1.id)?.status).toBe("ROLLED_BACK");

    store.close();

    // Restart
    const store2 = new SQLiteLedgerStore(DB_PATH);
    const ledger2 = new Ledger({ store: store2 });

    const entries = ledger2.getEntries();
    expect(entries.length).toBe(3);
    expect(entries.find(e => e.id === entry1.id)?.status).toBe("ROLLED_BACK");

    store2.close();
  });

  it("should clear database on clear()", () => {
    const store = new SQLiteLedgerStore(DB_PATH);
    const ledger = new Ledger({ store });

    ledger.append(
      { tool: "test", input: {}, output: {} },
      {}, {}, { verdict: "PASS", reason: "X" }
    );

    expect(ledger.getEntries().length).toBe(1);
    ledger.clear();
    expect(ledger.getEntries().length).toBe(0);

    store.close();

    // Restart should be empty
    const store2 = new SQLiteLedgerStore(DB_PATH);
    const ledger2 = new Ledger({ store: store2 });
    expect(ledger2.getEntries().length).toBe(0);
    store2.close();
  });
});
