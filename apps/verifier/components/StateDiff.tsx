"use client";

export function StateDiff({ before, after }: { before: unknown; after: unknown }) {
  const beforeStr = stringify(before);
  const afterStr = stringify(after);

  if (beforeStr === afterStr) {
    return <p className="text-[var(--color-text-faint)]">no state change</p>;
  }

  const lines = diffLines(beforeStr, afterStr);

  return (
    <div className="overflow-x-auto scroll-mono">
      <pre className="text-[12px] leading-snug">
        {lines.map((l, i) => (
          <span
            key={i}
            className={
              l.tag === "add"
                ? "block bg-[rgba(74,222,128,0.10)] text-[var(--color-success)]"
                : l.tag === "del"
                ? "block bg-[rgba(239,68,68,0.10)] text-[var(--color-danger)]"
                : "block text-[var(--color-text-muted)]"
            }
          >
            <span className="select-none mr-2 text-[var(--color-text-faint)]">
              {l.tag === "add" ? "+" : l.tag === "del" ? "-" : " "}
            </span>
            {l.text}
          </span>
        ))}
      </pre>
    </div>
  );
}

function stringify(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

interface DiffLine {
  tag: "ctx" | "add" | "del";
  text: string;
}

function diffLines(a: string, b: string): DiffLine[] {
  const aLines = a.split("\n");
  const bLines = b.split("\n");
  const out: DiffLine[] = [];

  // Simple LCS-based diff. Adequate for state snapshots that are mostly identical.
  const lcs = buildLCS(aLines, bLines);
  let i = 0;
  let j = 0;
  for (const op of lcs) {
    if (op === "keep") {
      out.push({ tag: "ctx", text: aLines[i] });
      i++;
      j++;
    } else if (op === "del") {
      out.push({ tag: "del", text: aLines[i] });
      i++;
    } else {
      out.push({ tag: "add", text: bLines[j] });
      j++;
    }
  }
  return out;
}

function buildLCS(a: string[], b: string[]): Array<"keep" | "add" | "del"> {
  const m = a.length;
  const n = b.length;
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (a[i] === b[j]) dp[i][j] = dp[i + 1][j + 1] + 1;
      else dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const ops: Array<"keep" | "add" | "del"> = [];
  let i = 0;
  let j = 0;
  while (i < m && j < n) {
    if (a[i] === b[j]) {
      ops.push("keep");
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push("del");
      i++;
    } else {
      ops.push("add");
      j++;
    }
  }
  while (i < m) {
    ops.push("del");
    i++;
  }
  while (j < n) {
    ops.push("add");
    j++;
  }
  return ops;
}
