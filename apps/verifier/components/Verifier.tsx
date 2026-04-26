"use client";

import { useCallback, useEffect, useMemo, useState, useTransition } from "react";
import { verifyLedgerAction, type VerifyResponse } from "@/app/actions";
import { decodeLedgerFromFragmentClient, encodeLedgerForUrlClient } from "@/lib/share-client";
import { EmptyState } from "./EmptyState";
import { ResultBanner } from "./ResultBanner";
import { Timeline } from "./Timeline";

export interface InitialPayload {
  text?: string;
  source?: string;
  error?: string;
}

export function Verifier({ initial }: { initial?: InitialPayload }) {
  const [text, setText] = useState(initial?.text ?? "");
  const [response, setResponse] = useState<VerifyResponse | null>(null);
  const [source, setSource] = useState<string | undefined>(initial?.source);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [shareWarning, setShareWarning] = useState<string | null>(null);
  const [bootstrapError, setBootstrapError] = useState<string | null>(initial?.error ?? null);
  const [pending, startTransition] = useTransition();

  const handleVerify = useCallback(
    (raw: string, opts?: { source?: string }) => {
      setText(raw);
      setSource(opts?.source);
      setShareUrl(null);
      setShareWarning(null);
      startTransition(async () => {
        const res = await verifyLedgerAction(raw);
        setResponse(res);
      });
    },
    []
  );

  useEffect(() => {
    if (typeof window === "undefined") return;
    const hash = window.location.hash.replace(/^#/, "");
    if (!hash) return;
    (async () => {
      const decoded = await decodeLedgerFromFragmentClient(hash);
      if (decoded) {
        handleVerify(decoded, { source: "shared link" });
      } else {
        setBootstrapError("This shared link is invalid or corrupted.");
      }
    })();
  }, [handleVerify]);

  useEffect(() => {
    if (!response?.ok) {
      setShareUrl(null);
      return;
    }
    let cancelled = false;
    (async () => {
      const { fragment, truncated } = await encodeLedgerForUrlClient(text);
      if (cancelled) return;
      if (truncated) {
        setShareUrl(null);
        setShareWarning(
          "Ledger is too large to encode in a URL. The CLI and `?url=` param both support large ledgers."
        );
      } else {
        const base = typeof window !== "undefined" ? window.location.origin + window.location.pathname : "";
        setShareUrl(`${base}#${fragment}`);
        setShareWarning(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [response, text]);

  const handleReset = useCallback(() => {
    setText("");
    setResponse(null);
    setShareUrl(null);
    setSource(undefined);
    if (typeof window !== "undefined" && window.location.hash) {
      history.replaceState(null, "", window.location.pathname);
    }
  }, []);

  const showResults = response !== null;

  const layoutClass = useMemo(() => {
    if (!showResults) return "min-h-[calc(100dvh-4rem)] flex items-center";
    return "py-8 sm:py-12";
  }, [showResults]);

  return (
    <main className={layoutClass}>
      <div className="w-full max-w-5xl mx-auto px-4 sm:px-6">
        {bootstrapError ? (
          <div className="mb-6 px-4 py-3 rounded-lg border border-[var(--color-danger)]/40 bg-[var(--color-danger-soft)] text-sm text-[var(--color-danger)]">
            {bootstrapError}
          </div>
        ) : null}

        {!showResults ? (
          <EmptyState onSubmit={(t) => handleVerify(t)} pending={pending} />
        ) : (
          <div className="space-y-6">
            <ResultBanner
              response={response!}
              source={source}
              shareUrl={shareUrl}
              shareWarning={shareWarning}
              onReset={handleReset}
              pending={pending}
            />
            {response!.ok ? (
              <Timeline ledger={response!.ledger} corruptedAt={response!.result.corruptedAt} />
            ) : null}
          </div>
        )}
      </div>
    </main>
  );
}
