import { ImageResponse } from "next/og";

export const runtime = "nodejs";
export const alt = "MAP Verifier — paste an agent ledger, see what happened";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const BG = "#08090b";
const SURFACE = "#101216";
const BORDER = "#23262d";
const TEXT = "#f5f6f8";
const MUTED = "#9ba0ab";
const FAINT = "#5c6270";
const ACCENT = "#fb923c";
const SUCCESS = "#4ade80";
const SUCCESS_BG = "rgba(74,222,128,0.10)";
const DANGER = "#ef4444";
const DANGER_BG = "rgba(239,68,68,0.10)";

export default async function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: BG,
          backgroundImage: [
            `radial-gradient(800px 400px at 90% -10%, rgba(251,146,60,0.10), transparent 60%)`,
            `radial-gradient(600px 400px at -10% 110%, rgba(74,222,128,0.06), transparent 60%)`,
          ].join(", "),
          color: TEXT,
          padding: "60px 72px",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          fontFamily: "ui-sans-serif, system-ui, sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: 999,
              background: ACCENT,
            }}
          />
          <div style={{ fontSize: 22, fontWeight: 600, letterSpacing: -0.3 }}>map</div>
          <div style={{ fontSize: 22, color: FAINT }}>verifier</div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
          <div
            style={{
              fontSize: 88,
              fontWeight: 600,
              letterSpacing: -2.5,
              lineHeight: 1.02,
              display: "flex",
              flexDirection: "column",
            }}
          >
            <span>Paste an agent ledger.</span>
            <span style={{ color: MUTED }}>See what happened.</span>
          </div>

          <div style={{ display: "flex", gap: 24 }}>
            <ResultCard
              tone="success"
              verb="Verified"
              copy="Every entry hashes, every link checks."
            />
            <ResultCard
              tone="danger"
              verb="Tampered"
              copy="Chain breaks at entry #1."
            />
          </div>
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            color: FAINT,
            fontSize: 22,
          }}
        >
          <div style={{ fontFamily: "ui-monospace, Menlo, monospace" }}>
            verify.modelactionprotocol.org
          </div>
          <div>by deadpxl</div>
        </div>
      </div>
    ),
    { ...size }
  );
}

function ResultCard({
  tone,
  verb,
  copy,
}: {
  tone: "success" | "danger";
  verb: string;
  copy: string;
}) {
  const accent = tone === "success" ? SUCCESS : DANGER;
  const bg = tone === "success" ? SUCCESS_BG : DANGER_BG;
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        padding: "20px 24px",
        borderRadius: 14,
        border: `1px solid ${accent}`,
        background: `${bg}`,
        boxShadow: `inset 0 0 0 1px ${BORDER}`,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
          color: accent,
          fontFamily: "ui-monospace, Menlo, monospace",
          fontSize: 18,
          letterSpacing: 3,
          textTransform: "uppercase",
        }}
      >
        <div
          style={{
            width: 12,
            height: 12,
            borderRadius: 999,
            background: accent,
            boxShadow: `0 0 0 4px ${bg}`,
          }}
        />
        <span>{verb}</span>
      </div>
      <div
        style={{
          fontSize: 26,
          color: TEXT,
          letterSpacing: -0.5,
          lineHeight: 1.15,
        }}
      >
        {copy}
      </div>
      <div
        style={{
          display: "flex",
          gap: 16,
          color: MUTED,
          fontFamily: "ui-monospace, Menlo, monospace",
          fontSize: 16,
          marginTop: 4,
        }}
      >
        <span>map · 0.1.0</span>
        <span>·</span>
        <span>4 entries</span>
      </div>
    </div>
  );
}
