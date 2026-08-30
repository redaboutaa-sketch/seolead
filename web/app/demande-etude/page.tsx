import type { Metadata } from "next";

import { RequestStudyPage } from "@/components/RequestStudyPage";

export const metadata: Metadata = {
  title: "Demander une estimation",
  description:
    "Quelques questions sur votre logement et votre toiture pour cadrer une estimation d'installation photovoltaïque.",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

/**
 * The French conversion page. The body lives in `RequestStudyPage`, shared with
 * `/nl/demande-etude`, so the two locale routes cannot diverge structurally —
 * only the locale (and therefore the resolved copy) differs.
 */
export default async function RequestPage() {
  return <RequestStudyPage locale="fr" />;
}
