import {
  Assurances,
  Benefits,
  Faq,
  FinalCta,
  Hero,
  Method,
  Process,
  QualificationCta,
} from "@/components/home/Sections";
import { getSiteConfig, listPublished } from "@/lib/api";

export const revalidate = 300;

/**
 * The homepage is composition, not markup.
 *
 * It remains a server component with no client-side JavaScript: every section
 * below is static, the FAQ uses native `<details>`, and the mobile CTA is a
 * `position: sticky` element rather than a scroll listener. That is what keeps
 * the performance criterion in US-SL-01 §10 true.
 *
 * Section order and the reasoning for each one — including why the brief's
 * proposed "savings visual" section is a method section here — are in
 * `docs/site/DESIGN_SYSTEM.md` §8.
 */
export default async function Home() {
  const config = await getSiteConfig();
  const locale = config?.default_language ?? "fr";
  const published = await listPublished(locale);

  return (
    <>
      <Hero config={config} locale={locale} />
      <Assurances />
      <Benefits />
      <Process />
      <Method config={config} published={published} />
      <QualificationCta config={config} locale={locale} />
      <Faq config={config} locale={locale} />
      <FinalCta config={config} locale={locale} />
    </>
  );
}
