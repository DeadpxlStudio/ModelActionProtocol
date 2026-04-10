import Database from "better-sqlite3";
import type { LedgerStore } from "../store.js";
import type { LedgerEntry, LedgerEntryStatus } from "../protocol.js";

/**
 * SQLite implementation of the LedgerStore.
 * 
 * Persists entries to a local SQLite database file using better-sqlite3.
 * Handles JSON serialization for complex objects (action, snapshots, critic).
 */
export class SQLiteLedgerStore implements LedgerStore {
  private db: Database.Database;

  constructor(path: string = "map.db") {
    this.db = new Database(path);
    this.init();
  }

  private init() {
    // Create the entries table if it doesn't exist.
    // We store complex objects as JSON strings.
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS entries (
        id TEXT PRIMARY KEY,
        sequence INTEGER NOT NULL,
        timestamp TEXT NOT NULL,
        action TEXT NOT NULL,
        stateBefore TEXT NOT NULL,
        stateAfter TEXT NOT NULL,
        snapshots TEXT NOT NULL,
        parentHash TEXT NOT NULL,
        hash TEXT NOT NULL,
        critic TEXT NOT NULL,
        status TEXT NOT NULL,
        approval TEXT,
        agentId TEXT,
        parentEntryId TEXT,
        lineage TEXT,
        stateVersion INTEGER
      );
      CREATE INDEX IF NOT EXISTS idx_entries_sequence ON entries(sequence);
    `);
  }

  append(entry: LedgerEntry): void {
    const stmt = this.db.prepare(`
      INSERT INTO entries (
        id, sequence, timestamp, action, stateBefore, stateAfter, 
        snapshots, parentHash, hash, critic, status, approval,
        agentId, parentEntryId, lineage, stateVersion
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `);

    stmt.run(
      entry.id,
      entry.sequence,
      entry.timestamp,
      JSON.stringify(entry.action),
      entry.stateBefore,
      entry.stateAfter,
      JSON.stringify(entry.snapshots),
      entry.parentHash,
      entry.hash,
      JSON.stringify(entry.critic),
      entry.status,
      entry.approval || null,
      entry.agentId || null,
      entry.parentEntryId || null,
      entry.lineage ? JSON.stringify(entry.lineage) : null,
      entry.stateVersion || null
    );
  }

  getEntries(): LedgerEntry[] {
    const rows = this.db.prepare("SELECT * FROM entries ORDER BY sequence ASC").all();
    return rows.map((row: any) => this.mapRowToEntry(row));
  }

  getEntry(id: string): LedgerEntry | undefined {
    const row = this.db.prepare("SELECT * FROM entries WHERE id = ?").get(id);
    return row ? this.mapRowToEntry(row) : undefined;
  }

  updateStatus(id: string, status: LedgerEntryStatus): void {
    this.db.prepare("UPDATE entries SET status = ? WHERE id = ?").run(status, id);
  }

  clear(): void {
    this.db.prepare("DELETE FROM entries").run();
  }

  private mapRowToEntry(row: any): LedgerEntry {
    return {
      id: row.id,
      sequence: row.sequence,
      timestamp: row.timestamp,
      action: JSON.parse(row.action),
      stateBefore: row.stateBefore,
      stateAfter: row.stateAfter,
      snapshots: JSON.parse(row.snapshots),
      parentHash: row.parentHash,
      hash: row.hash,
      critic: JSON.parse(row.critic),
      status: row.status as LedgerEntryStatus,
      approval: row.approval || undefined,
      agentId: row.agentId || undefined,
      parentEntryId: row.parentEntryId || undefined,
      lineage: row.lineage ? JSON.parse(row.lineage) : undefined,
      stateVersion: row.stateVersion || undefined,
    };
  }

  close(): void {
    this.db.close();
  }
}
