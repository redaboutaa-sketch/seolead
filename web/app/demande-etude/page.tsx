import type { Metadata } from "next";

import { RequestStudyPage } from "@/components/RequestStudyPage";
import { getSiteConfig } from "@/lib/api";
import { graph, organizationNode, webPageNode, websiteNode } from "@/lib/jsonld";
import { pageMetadata } from "@/lib/metadata";

// Écrits une fois, lus par les métas et par le balisage : deux formulations
// de la même page se contrediraient tôt ou tard.
const PATH = "/demande-etude";
const TITLE = "Demander une estimation";
const DESCRIPTION =
  "Quelques questions sur votre logement et votre toiture pour cadrer une " +
  "estimation d'installation photovoltaïque.";

// Robots follow the site-wide gate: this route is in the declared route table,
// so the sitemap lists it once the site is indexable — a hardcoded noindex
// here would then contradict the sitemap (found by the pre-publication crawl).
export async function generateMetadata(): Promise<Metadata> {
  const config = await getSiteConfig();
  return pageMetadata({ config, title: TITLE, description: DESCRIPTION,
                        path: PATH });
}

export const dynamic = "force-dynamic";

/**
 * The French conversion page. The body lives in `RequestStudyPage`, shared with
 * `/nl/demande-etude`, so the two locale routes cannot diverge structurally —
 * only the locale (and therefore the resolved copy) differs.
 */
export default async function RequestPage() {
  // Aucune donnée structurée ici jusqu'au 2026-09-10. C'est la page qui
  // répond à « comment demander une étude ? », l'une des sept questions du
  // protocole GEO : elle se nomme, et nomme qui l'opère.
  const config = await getSiteConfig();
  const jsonLd = graph(
    websiteNode(config),
    organizationNode(config),
    webPageNode(config, PATH, TITLE, DESCRIPTION),
  );

  return (
    <>
      {jsonLd ? (
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: jsonLd }}
        />
      ) : null}
      <RequestStudyPage locale="fr" />
    </>
  );
}
