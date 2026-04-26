"use client";

import type { ExportedLedger } from "@/lib/verify";
import { EntryCard } from "./EntryCard";

export function Timeline({ ledger, corruptedAt }: { ledger: ExportedLedger; corruptedAt?: number }) {
  if (!ledger.entries.length) {
    return (
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-8 text-center text-sm text-[var(--color-text-muted)]">
        Empty ledger — no entries yet.
      </div>
    );
  }

  return (
    <ol className="relative space-y-3">
      <span
        aria-hidden
        className="absolute left-[15px] top-2 bottom-2 w-px bg-[var(--color-border)]"
      />
      {ledger.entries.map((entry, i) => (
        <EntryCard
          key={entry.id ?? i}
          entry={entry}
          index={i}
          breakAt={corruptedAt}
          previousEntry={i > 0 ? ledger.entries[i - 1] : null}
        />
      ))}
    </ol>
  );
}
