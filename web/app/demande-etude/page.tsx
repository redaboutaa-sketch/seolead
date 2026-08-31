import type { Metadata } from "next";

import { RequestStudyPage } from "@/components/RequestStudyPage";
import { getSiteConfig } from "@/lib/api";
import { pageMetadata } from "@/lib/metadata";

// Robots follow the site-wide gate: this route is in the declared route table,
// so the sitemap lists it once the site is indexable — a hardcoded noindex
// here would then contradict the sitemap (found by the pre-publication crawl).
export async function generateMetadata(): Promise<Metadata> {
  const config = await getSiteConfig();
  return pageMetadata({
    config,
    title: "Demander une estimation",
    description:
      "Quelques questions sur votre logement et votre toiture pour cadrer une estimation d'installation photovoltaïque.",
    path: "/demande-etude",
  });
}

export const dynamic = "force-dynamic";

/**
 * The French conversion page. The body lives in `RequestStudyPage`, shared with
 * `/nl/demande-etude`, so the two locale routes cannot diverge structurally —
 * only the locale (and therefore the resolved copy) differs.
 */
export default async function RequestPage() {
  return <RequestStudyPage locale="fr" />;
}
