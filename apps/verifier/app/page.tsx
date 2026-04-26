import { Verifier, type InitialPayload } from "@/components/Verifier";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { fetchLedgerFromUrl } from "./actions";

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const urlParam = typeof sp.url === "string" ? sp.url : undefined;

  let initial: InitialPayload | undefined;
  if (urlParam) {
    const fetched = await fetchLedgerFromUrl(urlParam);
    if (fetched.ok) {
      initial = { text: fetched.text, source: urlParam };
    } else {
      initial = { error: fetched.error };
    }
  }

  return (
    <div className="flex flex-col min-h-[100dvh]">
      <Header />
      <Verifier initial={initial} />
      <Footer />
    </div>
  );
}
