"use client";

import { useState } from "react";
import type { VerifyResponse } from "@/app/actions";
import type { VerifyResult } from "@/lib/verify";
import { Check, AlertTriangle, Copy, RotateCcw, ExternalLink } from "./icons";

const SHARE_INTENT = "https://x.com/intent/post";

export function ResultBanner({
  response,
  source,
  shareUrl,
  shareWarning,
  onReset,
  pending,
}: {
  response: VerifyResponse;
  source?: string;
  shareUrl: string | null;
  shareWarning: string | null;
  onReset: () => void;
  pending: boolean;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    if (!shareUrl) return;
    await navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  };

  const tweetIntent = (() => {
    if (!response.ok || !shareUrl) return null;
    const text = response.result.valid
      ? "verified an agent ledger with the MAP verifier — chain intact, every action accounted for"
      : `caught a tampered agent ledger with the MAP verifier — chain breaks at entry #${response.result.corruptedAt}`;
    const params = new URLSearchParams({ text, url: shareUrl });
    return `${SHARE_INTENT}?${params.toString()}`;
  })();

  if (!response.ok) {
    return (
      <div className="rounded-xl border border-[var(--color-danger)]/40 bg-[var(--color-danger-soft)] px-5 py-4">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-2 text-sm font-semibold text-[var(--color-danger)]">
              <AlertTriangle className="size-4" />
              Could not parse
            </div>
            <p className="text-sm text-[var(--color-text-muted)] font-mono">{response.error}</p>
          </div>
          <button
            type="button"
            onClick={onReset}
            className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
          >
            <RotateCcw className="size-3.5" />
            Start over
          </button>
        </div>
      </div>
    );
  }

  const { result } = response;
  const tone = result.valid
    ? {
        accent: "var(--color-success)",
        bg: "var(--color-success-soft)",
        verb: "Verified",
        Icon: Check,
        copy: "Every entry hashes, every link checks.",
      }
    : {
        accent: "var(--color-danger)",
        bg: "var(--color-danger-soft)",
        verb: "Tampered",
        Icon: AlertTriangle,
        copy:
          result.corruptedAt !== undefined
            ? `Chain breaks at entry #${result.corruptedAt}. Every entry after this is suspect.`
            : "The ledger chain is broken.",
      };

  return (
    <div
      className="relative rounded-xl border px-5 py-5 sm:px-6 overflow-hidden"
      style={{
        borderColor: tone.accent,
        background: `linear-gradient(180deg, ${tone.bg}, transparent 70%), var(--color-surface)`,
      }}
    >
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs uppercase tracking-[0.18em] font-mono" style={{ color: tone.accent }}>
            <tone.Icon className="size-3.5" />
            {tone.verb}
          </div>
          <p className="text-2xl sm:text-3xl font-semibold tracking-[-0.02em] text-balance">
            {tone.copy}
          </p>
          {source && (
            <p className="text-xs text-[var(--color-text-faint)] font-mono">source: {source}</p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {shareUrl && (
            <button
              type="button"
              onClick={handleCopy}
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-border-strong)] transition-colors"
            >
              <Copy className="size-3.5" />
              {copied ? "Copied" : "Copy link"}
            </button>
          )}
          {tweetIntent && (
            <a
              href={tweetIntent}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-border-strong)] transition-colors"
            >
              Share on X
              <ExternalLink className="size-3" />
            </a>
          )}
          <button
            type="button"
            onClick={onReset}
            className="inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs text-[var(--color-text-faint)] hover:text-[var(--color-text-muted)] transition-colors"
          >
            <RotateCcw className="size-3.5" />
            Reset
          </button>
        </div>
      </div>

      <Stats result={result} />

      {shareWarning && (
        <p className="mt-3 text-xs text-[var(--color-warn)]">{shareWarning}</p>
      )}
      {pending && <p className="mt-3 text-xs text-[var(--color-text-faint)]">re-verifying…</p>}
    </div>
  );
}

function Stats({ result }: { result: VerifyResult }) {
  const fields: Array<{ label: string; value: string | number; tone?: "warn" | "danger" | "success" }> = [
    { label: "protocol", value: result.protocol ?? "—" },
    { label: "version", value: result.version ?? "—" },
    { label: "entries", value: result.total },
    { label: "committed", value: result.committed, tone: "success" },
    { label: "rolled back", value: result.rolledBack, tone: result.rolledBack > 0 ? "warn" : undefined },
    { label: "corrections", value: result.corrections, tone: result.corrections > 0 ? "warn" : undefined },
    { label: "flags", value: result.flags, tone: result.flags > 0 ? "danger" : undefined },
  ];

  return (
    <dl className="mt-5 grid grid-cols-3 sm:grid-cols-7 gap-3 sm:gap-2 text-xs font-mono">
      {fields.map((f) => (
        <div key={f.label} className="space-y-0.5">
          <dt className="text-[var(--color-text-faint)] uppercase tracking-wider text-[10px]">{f.label}</dt>
          <dd
            className="text-base text-[var(--color-text)]"
            style={{
              color:
                f.tone === "warn" ? "var(--color-warn)" :
                f.tone === "danger" ? "var(--color-danger)" :
                f.tone === "success" ? "var(--color-success)" :
                undefined,
            }}
          >
            {f.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
