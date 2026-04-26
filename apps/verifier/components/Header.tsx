import Link from "next/link";

export function Header() {
  return (
    <header className="w-full border-b border-[var(--color-border)]/60 bg-[var(--color-bg)]/80 backdrop-blur-md">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2 font-mono text-sm">
          <span className="size-1.5 rounded-full bg-[var(--color-accent)]" />
          <span className="font-semibold tracking-tight">map</span>
          <span className="text-[var(--color-text-faint)]">verifier</span>
        </Link>
        <nav className="flex items-center gap-1 sm:gap-3 text-xs">
          <a
            href="https://github.com/DeadpxlStudio/ModelActionProtocol"
            target="_blank"
            rel="noreferrer"
            className="px-2 py-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
          >
            GitHub
          </a>
          <a
            href="https://www.npmjs.com/package/@model-action-protocol/cli"
            target="_blank"
            rel="noreferrer"
            className="px-2 py-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
          >
            CLI
          </a>
          <a
            href="https://www.npmjs.com/package/@model-action-protocol/core"
            target="_blank"
            rel="noreferrer"
            className="px-2 py-1 text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors"
          >
            <span className="hidden sm:inline">@model-action-protocol/core</span>
            <span className="sm:hidden">npm</span>
          </a>
        </nav>
      </div>
    </header>
  );
}
