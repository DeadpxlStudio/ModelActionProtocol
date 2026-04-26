import { Verifier, type InitialPayload } from "@/components/Verifier";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { fetchLedgerFromUrl } from "../actions";

const DEMO_URL = "https://verify.modelactionprotocol.org/sample-tampered.ledger.json";

export default async function DemoPage() {
  const fetched = await fetchLedgerFromUrl(DEMO_URL);
  const initial: InitialPayload = fetched.ok
    ? { text: fetched.text, source: DEMO_URL }
    : { error: fetched.error };

  return (
    <div className="flex flex-col min-h-[100dvh]">
      <Header />
      <Verifier initial={initial} />
      <Footer />
    </div>
  );
}
