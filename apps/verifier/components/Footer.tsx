export function Footer() {
  return (
    <footer className="mt-auto border-t border-[var(--color-border)]/60">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 flex flex-col sm:flex-row gap-3 sm:items-center sm:justify-between text-xs text-[var(--color-text-faint)]">
        <div className="space-y-1">
          <div className="font-mono">
            <span className="text-[var(--color-text-muted)]">$</span>{" "}
            <span className="text-[var(--color-text)]">npx -p @model-action-protocol/cli map verify</span>{" "}
            <span className="text-[var(--color-accent)]">./agent.ledger.json</span>
          </div>
          <p>verify a ledger from your terminal — same code as this page</p>
        </div>
        <div className="flex items-center gap-3">
          <span>by</span>
          <a
            href="https://deadpxl.studio"
            target="_blank"
            rel="noreferrer"
            className="text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
          >
            deadpxl
          </a>
        </div>
      </div>
    </footer>
  );
}
