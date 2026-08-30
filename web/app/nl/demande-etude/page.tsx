import type { Metadata } from "next";

import { RequestStudyPage } from "@/components/RequestStudyPage";

/**
 * The Dutch conversion route — MECHANICS ONLY.
 *
 * Every visible string on this route resolves through the i18n fallback chain:
 * `i18n.nl` placeholders marked « À TRADUIRE PAR UN NATIF » where they exist,
 * the French base text where they do not. Nothing here is machine-translated,
 * and nothing here may ship as-is: the route exists so that the day a native
 * translation lands, the change is text, not plumbing.
 *
 * The locale is the load-bearing part: `locale="nl"` travels through LeadForm's
 * `language` field, is validated server-side against `supported_languages`, and
 * lands in `lead_attribution.language` and the export payload's
 * `attribution.locale`.
 */
export const metadata: Metadata = {
  title: "[NL — À TRADUIRE PAR UN NATIF] Demander une estimation",
  description:
    "[NL — À TRADUIRE PAR UN NATIF] Quelques questions sur votre logement et votre toiture pour cadrer une estimation d'installation photovoltaïque.",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function RequestPageNl() {
  return <RequestStudyPage locale="nl" />;
}
