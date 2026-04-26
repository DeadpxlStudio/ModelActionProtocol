"use client";

import { useCallback, useRef, useState, type DragEvent, type FormEvent } from "react";
import { ArrowRight, FileJson } from "./icons";

const SAMPLE_VALID = "/sample-valid.ledger.json";
const SAMPLE_TAMPERED = "/sample-tampered.ledger.json";

export function EmptyState({
  onSubmit,
  pending,
}: {
  onSubmit: (text: string) => void;
  pending: boolean;
}) {
  const [text, setText] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    async (e: DragEvent<HTMLFormElement>) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (!file) return;
      const t = await file.text();
      setText(t);
      onSubmit(t);
    },
    [onSubmit]
  );

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      if (!text.trim()) return;
      onSubmit(text);
    },
    [onSubmit, text]
  );

  const loadSample = useCallback(
    async (url: string) => {
      const res = await fetch(url);
      const t = await res.text();
      setText(t);
      onSubmit(t);
    },
    [onSubmit]
  );

  return (
    <div className="space-y-8">
      <div className="space-y-3 text-center">
        <p className="inline-flex items-center gap-2 text-xs uppercase tracking-[0.18em] text-[var(--color-text-faint)] font-mono">
          <span className="size-1.5 rounded-full bg-[var(--color-accent)]" />
          MAP Verifier
        </p>
        <h1 className="text-3xl sm:text-5xl font-semibold tracking-[-0.02em] text-balance">
          Paste an agent ledger.
          <br />
          <span className="text-[var(--color-text-muted)]">See what happened.</span>
        </h1>
        <p className="text-[var(--color-text-muted)] text-sm sm:text-base max-w-xl mx-auto">
          The Model Action Protocol logs every autonomous agent action with a hash-chained, tamper-evident receipt. Paste one here to verify it end-to-end in your browser.
        </p>
      </div>

      <form
        onSubmit={handleSubmit}
        className={`relative rounded-xl border bg-[var(--color-surface)] transition-colors ${
          dragging
            ? "border-[var(--color-accent)] bg-[var(--color-accent-soft)]"
            : "border-[var(--color-border)] hover:border-[var(--color-border-strong)]"
        }`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder='{"protocol": "map", "version": "0.1.0", "entries": [...]}'
          spellCheck={false}
          rows={10}
          className="w-full resize-none bg-transparent px-5 py-4 font-mono text-[13px] leading-relaxed text-[var(--color-text)] placeholder:text-[var(--color-text-faint)] focus:outline-none scroll-mono"
        />
        <div className="flex flex-wrap items-center justify-between gap-3 px-3 pb-3 pt-1 sm:px-4 sm:pb-4">
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="inline-flex items-center gap-1.5 rounded-md border border-[var(--color-border)] bg-[var(--color-surface-2)] px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:border-[var(--color-border-strong)] transition-colors"
            >
              <FileJson className="size-3.5" />
              Open file
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="application/json,.json"
              hidden
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                const t = await file.text();
                setText(t);
                onSubmit(t);
              }}
            />
            <button
              type="button"
              onClick={() => loadSample(SAMPLE_VALID)}
              className="rounded-md px-2.5 py-1.5 text-xs text-[var(--color-text-faint)] hover:text-[var(--color-text-muted)] transition-colors"
            >
              try a sample
            </button>
            <button
              type="button"
              onClick={() => loadSample(SAMPLE_TAMPERED)}
              className="rounded-md px-2.5 py-1.5 text-xs text-[var(--color-text-faint)] hover:text-[var(--color-warn)] transition-colors"
            >
              try a tampered one
            </button>
          </div>
          <button
            type="submit"
            disabled={pending || !text.trim()}
            className="inline-flex items-center gap-1.5 rounded-md bg-[var(--color-accent)] px-3.5 py-1.5 text-xs font-medium text-[var(--color-bg)] hover:brightness-110 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {pending ? "Verifying…" : "Verify"}
            {!pending && <ArrowRight className="size-3.5" />}
          </button>
        </div>
        {dragging && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-xl text-sm text-[var(--color-accent)]">
            drop the .ledger.json
          </div>
        )}
      </form>

      <p className="text-center text-xs text-[var(--color-text-faint)]">
        nothing leaves your browser unless you click <span className="font-mono text-[var(--color-text-muted)]">Verify</span>
      </p>
    </div>
  );
}
