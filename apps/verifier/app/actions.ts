"use server";

import { parseLedger, verifyLedger, type ExportedLedger, type VerifyResult } from "@/lib/verify";

const MAX_BYTES = 5 * 1024 * 1024;

export type VerifyResponse =
  | { ok: true; result: VerifyResult; ledger: ExportedLedger }
  | { ok: false; error: string };

export async function verifyLedgerAction(text: string): Promise<VerifyResponse> {
  if (!text.trim()) {
    return { ok: false, error: "Paste a ledger JSON to verify." };
  }
  if (text.length > MAX_BYTES) {
    return {
      ok: false,
      error: `Ledger is too large (${(text.length / 1024 / 1024).toFixed(1)} MB). Max 5 MB.`,
    };
  }
  try {
    const ledger = parseLedger(text);
    const result = verifyLedger(ledger);
    return { ok: true, result, ledger };
  } catch (err) {
    return { ok: false, error: (err as Error).message };
  }
}

export async function fetchLedgerFromUrl(url: string): Promise<{ ok: true; text: string } | { ok: false; error: string }> {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return { ok: false, error: "Invalid URL." };
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    return { ok: false, error: "URL must be http or https." };
  }
  try {
    const res = await fetch(parsed.toString(), {
      headers: { accept: "application/json" },
      signal: AbortSignal.timeout(10_000),
    });
    if (!res.ok) {
      return { ok: false, error: `Fetch failed: ${res.status} ${res.statusText}` };
    }
    const text = await res.text();
    if (text.length > MAX_BYTES) {
      return { ok: false, error: "Remote ledger too large (max 5 MB)." };
    }
    return { ok: true, text };
  } catch (err) {
    return { ok: false, error: `Could not fetch ledger: ${(err as Error).message}` };
  }
}
