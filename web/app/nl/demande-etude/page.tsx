import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { RequestStudyPage } from "@/components/RequestStudyPage";
import { getSiteConfig } from "@/lib/api";

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
 *
 * SERVED ONLY WHEN THE SITE DECLARES THE LOCALE. The owner decided on
 * 2026-08-31 that this campaign is French only, so `supported_languages` no
 * longer lists `nl` and this route 404s. The file stays: deleting it would
 * throw away working plumbing that a Dutch campaign will want back, and the
 * server would refuse a `language: "nl"` submission anyway — a page that can
 * only collect a rejection has no business being reachable.
 *
 * Re-declaring the locale in `config/sites/solar_be.yaml` turns it back on, and
 * the `pending_legal_review` guard resumes blocking until the Dutch consent
 * texts are validated. That is the intended behaviour, not a leftover.
 */
export const metadata: Metadata = {
  title: "[NL — À TRADUIRE PAR UN NATIF] Demander une estimation",
  description:
    "[NL — À TRADUIRE PAR UN NATIF] Quelques questions sur votre logement et votre toiture pour cadrer une estimation d'installation photovoltaïque.",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function RequestPageNl() {
  const config = await getSiteConfig();
  if (!config?.supported_languages?.includes("nl")) {
    notFound();
  }
  return <RequestStudyPage locale="nl" />;
}
