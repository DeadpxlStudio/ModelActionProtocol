"use client";

import { useState } from "react";
import type { LedgerEntry } from "@model-action-protocol/core";
import { Check, AlertTriangle, ChevronDown, Wand, Hand } from "./icons";
import { StateDiff } from "./StateDiff";

const VERDICT_TONE = {
  PASS: { color: "var(--color-success)", bg: "var(--color-success-soft)", Icon: Check, label: "passed" },
  CORRECTED: { color: "var(--color-warn)", bg: "rgba(250,204,21,0.10)", Icon: Wand, label: "auto-corrected" },
  FLAGGED: { color: "var(--color-danger)", bg: "var(--color-danger-soft)", Icon: Hand, label: "flagged" },
} as const;

export function EntryCard({
  entry,
  index,
  breakAt,
  previousEntry,
}: {
  entry: LedgerEntry;
  index: number;
  breakAt?: number;
  previousEntry: LedgerEntry | null;
}) {
  const [open, setOpen] = useState(false);

  const verdict = entry.critic?.verdict ?? "PASS";
  const tone = VERDICT_TONE[verdict] ?? VERDICT_TONE.PASS;
  const isBreakPoint = breakAt !== undefined && index === breakAt;
  const isAfterBreak = breakAt !== undefined && index > breakAt;

  return (
    <li className="relative pl-12">
      <span
        aria-hidden
        className="absolute left-2 top-4 size-3 rounded-full border-2 border-[var(--color-bg)]"
        style={{
          background: isBreakPoint ? "var(--color-danger)" : tone.color,
          boxShadow: isBreakPoint ? "0 0 0 3px rgba(239,68,68,0.25)" : undefined,
        }}
      />
      <article
        className={`group rounded-lg border bg-[var(--color-surface)] transition-colors ${
          isBreakPoint
            ? "border-[var(--color-danger)]/60"
            : isAfterBreak
            ? "border-[var(--color-border)] opacity-60"
            : "border-[var(--color-border)] hover:border-[var(--color-border-strong)]"
        }`}
      >
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="w-full flex items-start justify-between gap-3 px-4 py-3 text-left"
        >
          <div className="flex-1 min-w-0 space-y-1">
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-[10px] font-mono text-[var(--color-text-faint)] tabular-nums">
                #{entry.sequence}
              </span>
              <span className="font-mono text-sm text-[var(--color-text)]">
                {entry.action?.tool ?? "(unknown)"}
              </span>
              <span
                className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] uppercase tracking-wider font-mono"
                style={{ color: tone.color, background: tone.bg }}
              >
                <tone.Icon className="size-3" />
                {tone.label}
              </span>
              {entry.action?.reversalStrategy && (
                <span className="text-[10px] uppercase tracking-wider text-[var(--color-text-faint)] font-mono">
                  {entry.action.reversalStrategy}
                </span>
              )}
              {entry.status === "ROLLED_BACK" && (
                <span className="text-[10px] uppercase tracking-wider text-[var(--color-warn)] font-mono">
                  rolled back
                </span>
              )}
            </div>
            <p className="text-xs text-[var(--color-text-muted)] truncate">
              {entry.critic?.reason ?? "—"}
            </p>
            {isBreakPoint && (
              <p className="text-xs text-[var(--color-danger)] flex items-center gap-1.5 mt-1">
                <AlertTriangle className="size-3.5" />
                hash mismatch — recomputed hash does not match recorded hash
              </p>
            )}
          </div>
          <ChevronDown
            className={`size-4 text-[var(--color-text-faint)] flex-shrink-0 transition-transform ${
              open ? "rotate-180" : ""
            }`}
          />
        </button>

        {open && (
          <div className="border-t border-[var(--color-border)] px-4 py-4 space-y-4 bg-[var(--color-surface-2)]/40">
            <Field label="input">
              <code className="block whitespace-pre overflow-x-auto scroll-mono">
                {prettyJson(entry.action?.input)}
              </code>
            </Field>
            <Field label="output">
              <code className="block whitespace-pre overflow-x-auto scroll-mono">
                {prettyJson(entry.action?.output)}
              </code>
            </Field>
            {entry.critic?.correction && (
              <Field label="critic correction">
                <code className="block whitespace-pre overflow-x-auto scroll-mono">
                  {prettyJson(entry.critic.correction)}
                </code>
              </Field>
            )}
            {entry.snapshots && (
              <Field label="state diff">
                <StateDiff before={entry.snapshots.before} after={entry.snapshots.after} />
              </Field>
            )}
            <div className="grid grid-cols-2 gap-3 text-[10px] font-mono text-[var(--color-text-faint)]">
              <div>
                <div className="uppercase tracking-wider mb-0.5">parent hash</div>
                <div className="break-all text-[var(--color-text-muted)]">
                  {entry.parentHash}
                  {previousEntry && entry.parentHash !== previousEntry.hash && (
                    <span className="ml-2 text-[var(--color-danger)]">
                      ≠ previous.hash {previousEntry.hash.slice(0, 8)}…
                    </span>
                  )}
                </div>
              </div>
              <div>
                <div className="uppercase tracking-wider mb-0.5">entry hash</div>
                <div className="break-all text-[var(--color-text-muted)]">{entry.hash}</div>
              </div>
              <div>
                <div className="uppercase tracking-wider mb-0.5">state before</div>
                <div className="break-all text-[var(--color-text-muted)]">{entry.stateBefore}</div>
              </div>
              <div>
                <div className="uppercase tracking-wider mb-0.5">state after</div>
                <div className="break-all text-[var(--color-text-muted)]">{entry.stateAfter}</div>
              </div>
              {entry.timestamp && (
                <div>
                  <div className="uppercase tracking-wider mb-0.5">timestamp</div>
                  <div className="text-[var(--color-text-muted)]">{entry.timestamp}</div>
                </div>
              )}
              {entry.agentId && (
                <div>
                  <div className="uppercase tracking-wider mb-0.5">agent</div>
                  <div className="text-[var(--color-text-muted)]">{entry.agentId}</div>
                </div>
              )}
            </div>
          </div>
        )}
      </article>
    </li>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <div className="text-[10px] font-mono uppercase tracking-wider text-[var(--color-text-faint)]">
        {label}
      </div>
      <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 font-mono text-xs text-[var(--color-text-muted)]">
        {children}
      </div>
    </div>
  );
}

function prettyJson(value: unknown): string {
  if (value === undefined) return "(none)";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
