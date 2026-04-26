import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import "./globals.css";

const SITE_URL =
  process.env.NEXT_PUBLIC_SITE_URL ??
  (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : "https://verify.modelactionprotocol.org");

export const metadata: Metadata = {
  title: "MAP Verifier — paste an agent ledger, see what happened",
  description:
    "Paste any agent's ledger and verify every action, every critic verdict, every state diff — chain integrity proven end-to-end, in your browser.",
  metadataBase: new URL(SITE_URL),
  openGraph: {
    title: "MAP Verifier",
    description:
      "Paste an agent ledger. See what happened. Share a link.",
    url: SITE_URL,
    siteName: "Model Action Protocol",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "MAP Verifier",
    description: "Paste an agent ledger. See what happened. Share a link.",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
