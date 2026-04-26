// Client-side share helpers — uses CompressionStream so we don't ship node:zlib to the browser.

const MAX_ENCODED_LEN = 16_000;

function bytesToBase64Url(bytes: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function base64UrlToBytes(s: string): Uint8Array {
  const pad = "=".repeat((4 - (s.length % 4)) % 4);
  const b64 = (s + pad).replaceAll("-", "+").replaceAll("_", "/");
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export async function encodeLedgerForUrlClient(
  json: string
): Promise<{ fragment: string; truncated: boolean }> {
  if (typeof CompressionStream === "undefined") {
    return { fragment: "", truncated: true };
  }
  const stream = new Blob([json]).stream().pipeThrough(new CompressionStream("gzip"));
  const buf = await new Response(stream).arrayBuffer();
  const b64 = bytesToBase64Url(new Uint8Array(buf));
  if (b64.length > MAX_ENCODED_LEN) {
    return { fragment: "", truncated: true };
  }
  return { fragment: `l=${b64}`, truncated: false };
}

export async function decodeLedgerFromFragmentClient(
  fragment: string
): Promise<string | null> {
  if (!fragment.startsWith("l=") || typeof DecompressionStream === "undefined") return null;
  try {
    const bytes = base64UrlToBytes(fragment.slice(2));
    const stream = new Blob([bytes as BlobPart]).stream().pipeThrough(new DecompressionStream("gzip"));
    const text = await new Response(stream).text();
    return text;
  } catch {
    return null;
  }
}
